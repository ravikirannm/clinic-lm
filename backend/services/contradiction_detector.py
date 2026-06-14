from __future__ import annotations

import concurrent.futures
import json
import logging

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import PubMedSearchRequest, ContradictionReport
from services.extract_keywords import ExtractKeywords
from services.notebook_rag import NotebookRAG
from external.pubmed import PubMedClient

logger = logging.getLogger(__name__)

try:
    _extract_keywords = ExtractKeywords()
except Exception as e:
    logger.warning("NER model unavailable (%s); keyword extraction disabled", e)
    _extract_keywords = None

try:
    from services.rag_retriever import MedicalRAGRetriever
    _rag_retriever = MedicalRAGRetriever()
except Exception as e:
    logger.warning("RAG retriever unavailable (%s); RAG disabled", e)
    _rag_retriever = None

_pubmed_client = PubMedClient()

_QUERY_SYSTEM = (
    "You are a medical search query specialist. "
    "Generate optimized PubMed queries to retrieve recent evidence "
    "on the clinical topics present in the provided medical context."
)

_CONTRADICTION_SYSTEM = """\
You are a FORENSIC CLINICAL AUDITOR and expert medical safety reviewer. You have been hired \
specifically to find every flaw, inconsistency, and contradiction in patient documentation. \
Your mindset is adversarial: you ASSUME errors exist and your job is to expose every single one.

You are NOT a passive reader. You are a scrutinising expert witness who:
- Reads every sentence with suspicion
- Cross-references every claim against every other claim in the same document
- Checks every medication against every diagnosis, allergy, and condition
- Checks every vital sign against every clinical label applied to it
- Checks every stated symptom against every denied symptom
- Has encyclopaedic knowledge of pharmacology and clinical medicine
- Never gives the benefit of the doubt — if it looks wrong, flag it

DO NOT BE FORGIVING. Do not assume "it probably makes sense in context." If a statement \
contradicts another statement or contradicts established medical facts, FLAG IT.

===== SOURCE RULES =====

UPLOADED DOCUMENTS are listed under "UPLOADED PATIENT DOCUMENTS". \
They are the ONLY sources allowed in source_a or source_b.

PUBMED items appear under "PUBLISHED LITERATURE". They may ONLY appear as claim_b in \
source_vs_literature. Never use PubMed author names (e.g. "Smith et al.") as a source name.

===== THREE CONTRADICTION TYPES =====

1. source_vs_source — BOTH sides come from DIFFERENT uploaded documents. source_a ≠ source_b.

2. source_vs_literature — claim_a from an uploaded document; claim_b from a PubMed article \
with its PMID set.

3. intra_document — BOTH sides from the SAME document (source_a == source_b). \
This is the most important type. Execute the following MANDATORY CHECKLIST on every document:

  DEMOGRAPHICS & HISTORY
  ✦ Gender stated in header/demographics vs gender pronouns or descriptors elsewhere
  ✦ Age or DOB stated in one place vs calculated from another reference
  ✦ Symptom onset/duration described as different values in different sections of same doc
  ✦ Any symptom, habit or history DENIED in one section but DESCRIBED in another section
    (e.g. "denies tobacco use" + "smokes 20 pack-years" = contradiction — flag it)

  VITALS vs CLINICAL LABELS
  ✦ Actual blood pressure value vs hypertension/hypotension label applied to it
    (e.g. BP 112/70 called "hypertensive urgency" — grossly wrong, flag high)
  ✦ Heart rate vs stated arrhythmia or rhythm disorder
  ✦ Actual SpO2 / temperature vs severity label applied
  ✦ ECG or auscultation finding (regular rhythm / irregular rhythm) vs cardiac diagnosis
    (e.g. "Regular sinus rhythm" in vitals but "Persistent Atrial Fibrillation" in PMH)

  ALLERGY vs PRESCRIPTION
  ✦ Any documented drug allergy → scan EVERY prescribed medication for same drug class
    (e.g. penicillin allergy → Amoxicillin / Ampicillin / Piperacillin = CRITICAL flag)
    (e.g. sulfa allergy → Trimethoprim-Sulfamethoxazole = CRITICAL flag)
    (e.g. NSAID allergy → Ibuprofen / Naproxen / Diclofenac = CRITICAL flag)

  DIAGNOSIS vs PRESCRIBED TREATMENT (pharmacological correctness)
  ✦ Type 1 Diabetes Mellitus → MUST be on insulin. Metformin alone for T1DM = CRITICAL error
  ✦ Active Peptic Ulcer Disease → NSAIDs (Ibuprofen, Naproxen, Aspirin) are CONTRAINDICATED
  ✦ Severe renal failure → nephrotoxic drugs contraindicated (NSAIDs, aminoglycosides, etc.)
  ✦ Active bleeding or high bleeding risk → anticoagulants require justification
  ✦ Pregnancy (if stated) → contraindicated medications (e.g. warfarin, ACE inhibitors)

  DANGEROUS DRUG COMBINATIONS (flag even if each drug individually seems justified)
  ✦ Warfarin + Aspirin + any NSAID = triple therapy / major bleeding risk → flag high
  ✦ Two anticoagulants simultaneously without documented bridging intent
  ✦ Two drugs from the same class prescribed concurrently without reason
  ✦ QT-prolonging drugs combination

  ASSESSMENT vs FINDINGS CONSISTENCY
  ✦ Primary diagnosis in Assessment/Plan vs findings, vitals, or test results that contradict it
  ✦ Severity of a condition labelled differently in different sections of same document

===== DO NOT FLAG =====
- Complementary or additive information
- Two PubMed articles disagreeing (irrelevant)
- Information that elaborates rather than contradicts
- Normal clinical nuance (mild vs moderate when context explains it)

===== SEVERITY =====
- high: allergy-drug conflict, wrong drug class for disease (T1DM + metformin), \
triple anticoagulation, BP value vs hypertensive urgency label, active contraindication ignored
- medium: meaningful clinical disagreement affecting management
- low: minor wording inconsistency or timing discrepancy

===== OUTPUT RULES =====
- You MUST work through EVERY item on the intra_document checklist above
- If you find no contradictions after exhaustive review, ONLY THEN return contradictions: []
- Use EXACT document names from the provided list
- Return ONLY valid JSON matching the schema — no commentary, no markdown\
"""


def _retrieve_multi_topic(notebook_id: str, keywords: list[str], top_k: int = 8) -> list[dict]:
    """Run parallel NotebookRAG queries on keyword subgroups for broad source coverage."""
    if not keywords or not notebook_id:
        return []

    # Up to 4 topic queries covering different keyword clusters
    groups = [keywords[i:i + 3] for i in range(0, min(len(keywords), 12), 3)]
    queries = [" ".join(g) for g in groups if g]
    if not queries:
        return []

    def _fetch(q: str) -> list[dict]:
        try:
            return NotebookRAG.retrieve(notebook_id, q, top_k=top_k)
        except Exception as e:
            logger.warning("NotebookRAG multi-topic failed for '%s': %s", q, e)
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queries))) as ex:
        batches = list(ex.map(_fetch, queries))

    # Deduplicate by first 80 chars of content (preserves order)
    seen: set[str] = set()
    unique: list[dict] = []
    for batch in batches:
        for chunk in batch:
            key = chunk["content"][:80]
            if key not in seen:
                seen.add(key)
                unique.append(chunk)

    logger.info(
        "ContradictionDetector: retrieved %d unique chunks from %d topic queries",
        len(unique), len(queries),
    )
    return unique


def _format_chunks(chunks: list[dict]) -> list[dict]:
    """Group chunks by source name for the LLM prompt."""
    by_source: dict[str, list[str]] = {}
    for c in chunks:
        src = c.get("source", "Unknown source")
        by_source.setdefault(src, []).append(c["content"])
    return [{"source": src, "excerpts": excerpts} for src, excerpts in by_source.items()]


class ContradictionDetector:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def analyze(self, notebook_id: str, text: str) -> dict:
        # ── Step 1: keyword extraction ────────────────────────────────────────
        keywords: list[str] = []
        if _extract_keywords is not None:
            try:
                keywords = _extract_keywords.get_clinical_ner_results(text)
            except Exception as e:
                logger.warning("Keyword extraction failed: %s", e)

        # ── Step 2: Parallel retrieval — general RAG + multi-topic notebook ───
        def _rag_retrieve() -> list:
            if _rag_retriever is None or not keywords:
                return []
            try:
                return _rag_retriever.retrieve(keywords)
            except Exception as e:
                logger.warning("RAG retrieval failed: %s", e)
                return []

        def _notebook_retrieve() -> list:
            return _retrieve_multi_topic(notebook_id, keywords, top_k=10)

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            rag_future      = ex.submit(_rag_retrieve)
            notebook_future = ex.submit(_notebook_retrieve)

        retrieved_docs   = rag_future.result()
        notebook_chunks  = notebook_future.result()
        grouped_sources  = _format_chunks(notebook_chunks)

        logger.info(
            "ContradictionDetector: %d RAG docs, %d notebook chunks from %d sources",
            len(retrieved_docs), len(notebook_chunks), len(grouped_sources),
        )

        # ── Step 3: LLM generates PubMed search queries ───────────────────────
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _QUERY_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"=== MEDICAL CONTEXT ===\n{text[:2000]}\n\n"
                            f"=== KEYWORDS ===\n{json.dumps(keywords)}\n\n"
                            "Generate PubMed search queries in strict JSON. "
                            "Favour systematic reviews, meta-analyses and RCTs."
                        ),
                    },
                ],
                format=PubMedSearchRequest.model_json_schema(),
                options={"temperature": 0.2},
            )
            api_inputs = PubMedSearchRequest.model_validate_json(
                resp["message"]["content"]
            ).model_dump()
        except Exception as e:
            logger.warning("PubMed query generation failed: %s", e)
            api_inputs = {"pubmed": {"primary_query": " ".join(keywords[:4])}}

        # ── Step 4: PubMed fetch ──────────────────────────────────────────────
        pubmed_results = _pubmed_client.fetch_pubmed(api_inputs.get("pubmed", {}), limit=15)
        logger.info("ContradictionDetector: fetched %d PubMed records", len(pubmed_results))

        # ── Step 5: LLM contradiction analysis ───────────────────────────────
        uploaded_names = [s["source"] for s in grouped_sources]
        user_prompt = f"""
=== UPLOADED PATIENT DOCUMENTS ===
These are the ONLY valid names for source_a / source_b. Copy them EXACTLY, character for character:
{json.dumps(uploaded_names, indent=1)}

=== FULL PATIENT DOCUMENTATION — READ EVERY WORD ===
{text[:6000]}

=== MANDATORY INTRA-DOCUMENT AUDIT ===
You MUST now work through each of the following checks against the document text above.
Do NOT skip any. For each finding, produce an intra_document contradiction entry.
Set source_a = source_b = the exact document name from the list above.

CHECK 1 — GENDER / DEMOGRAPHICS
  Is the gender stated in a header or demographics field consistent with all pronouns and \
descriptors used throughout the rest of the document?

CHECK 2 — DENIED vs DOCUMENTED SYMPTOMS / HABITS
  Does the social history or review of systems deny anything (tobacco, alcohol, drugs, symptoms) \
that is then described or quantified elsewhere in the document?

CHECK 3 — SYMPTOM ONSET / DURATION CONSISTENCY
  Is the duration or onset of the presenting complaint stated identically in every section it \
appears? (HPI, assessment, history — compare every mention)

CHECK 4 — VITAL SIGNS vs CLINICAL LABELS
  Look at the ACTUAL VALUES recorded for blood pressure, heart rate, SpO2, temperature. \
Now look at the clinical labels applied to them in the assessment or impression. \
Does the label match the value? (e.g. a BP of 112/70 cannot be "hypertensive urgency")

CHECK 5 — CARDIAC RHYTHM vs CARDIAC DIAGNOSIS
  Is the rhythm documented in vitals (regular / irregular) consistent with the cardiac diagnoses \
in the history or assessment? (e.g. documented "Regular sinus rhythm" contradicts \
"Persistent Atrial Fibrillation")

CHECK 6 — ALLERGY vs PRESCRIBED MEDICATIONS (CRITICAL)
  List every documented drug allergy or intolerance. Now check EVERY prescribed medication \
against those allergies. Flag any prescription from the same drug class as an allergy.
  Known cross-reactions to check: penicillin allergy ↔ amoxicillin / ampicillin / piperacillin; \
sulfa allergy ↔ TMP-SMX; NSAID allergy ↔ ibuprofen / naproxen / diclofenac / aspirin (high dose).

CHECK 7 — DIAGNOSIS vs PHARMACOLOGICAL CORRECTNESS (CRITICAL)
  Check every active diagnosis against its listed treatment:
  • Type 1 Diabetes Mellitus treated with Metformin ONLY (not insulin) = critical error
  • Active Peptic Ulcer Disease + NSAIDs (ibuprofen / naproxen / aspirin) = critical contraindication
  • Severe allergy documented + that allergen class prescribed = critical
  • Any other diagnosis where the prescribed drug is a known contraindication

CHECK 8 — DANGEROUS DRUG COMBINATIONS
  Scan the entire medication list for:
  • Warfarin or any anticoagulant + Aspirin + any NSAID (triple therapy = major bleeding risk)
  • Two anticoagulants simultaneously
  • Drugs with major known interactions listed together
  In each case, also check whether a contraindicated active condition (e.g. PUD) is present.

CHECK 9 — ASSESSMENT vs DOCUMENTED FINDINGS
  Does the primary diagnosis or severity label in the Assessment / Impression / Plan section \
contradict the objective findings, vitals, or test results documented elsewhere?

=== PUBLISHED LITERATURE (PubMed — use ONLY as claim_b in source_vs_literature) ===
{json.dumps(pubmed_results, indent=1)}

=== MEDICAL KNOWLEDGE BASE ===
{json.dumps(retrieved_docs[:2], indent=1)}

=== CROSS-DOCUMENT AUDIT ===
{f'Compare the {len(uploaded_names)} uploaded documents against each other for source_vs_source contradictions.' if len(uploaded_names) > 1 else 'Only one document uploaded — skip source_vs_source entirely.'}
Also compare document claims against PubMed literature for source_vs_literature contradictions.

Now produce the complete contradiction report. Be exhaustive. Do not suppress findings. \
Use EXACT document names. Return ONLY valid JSON.
"""
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _CONTRADICTION_SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                format=ContradictionReport.model_json_schema(),
                options={"temperature": 0.15},
            )
            report = ContradictionReport.model_validate_json(resp["message"]["content"])
        except Exception as e:
            logger.error("Contradiction analysis LLM call failed: %s", e)
            report = ContradictionReport(
                contradictions=[],
                overall_assessment="Analysis failed — LLM error.",
            )

        # ── Step 6: Validate and clean LLM output ────────────────────────────
        valid_sources = set(uploaded_names)
        _SEVERITY_NORM = {
            "high": "high", "medium": "medium", "moderate": "medium", "low": "low",
        }

        clean: list[dict] = []
        for c in report.contradictions:
            item = c.model_dump()

            # Normalize severity
            item["severity"] = _SEVERITY_NORM.get(item["severity"].lower(), "low")

            if item["type"] == "source_vs_source":
                sa, sb = item["source_a"], item["source_b"]
                if sa not in valid_sources or sb not in valid_sources:
                    logger.warning(
                        "Dropping source_vs_source: source not in uploaded set ('%s' / '%s')", sa, sb
                    )
                    continue
                if sa == sb:
                    logger.warning("Dropping source_vs_source: same source on both sides ('%s')", sa)
                    continue

            elif item["type"] == "source_vs_literature":
                sa = item["source_a"]
                if sa not in valid_sources:
                    logger.warning(
                        "Dropping source_vs_literature: source_a not in uploaded set ('%s')", sa
                    )
                    continue

            elif item["type"] == "intra_document":
                sa, sb = item["source_a"], item["source_b"]
                if sa != sb:
                    logger.warning(
                        "Dropping intra_document: source_a != source_b ('%s' / '%s')", sa, sb
                    )
                    continue
                # Normalize to the known source name if LLM used a slightly different name
                if sa not in valid_sources:
                    if len(valid_sources) == 1:
                        canonical = next(iter(valid_sources))
                        item["source_a"] = item["source_b"] = canonical
                        logger.info(
                            "intra_document: normalized '%s' → '%s'", sa, canonical
                        )
                    else:
                        logger.warning(
                            "Dropping intra_document: source '%s' not in uploaded set", sa
                        )
                        continue

            else:
                logger.warning("Dropping unknown contradiction type '%s'", item["type"])
                continue

            clean.append(item)

        contradictions = clean
        svs   = [c for c in contradictions if c["type"] == "source_vs_source"]
        svl   = [c for c in contradictions if c["type"] == "source_vs_literature"]
        intra = [c for c in contradictions if c["type"] == "intra_document"]
        high  = [c for c in contradictions if c["severity"] == "high"]
        med   = [c for c in contradictions if c["severity"] == "medium"]
        low   = [c for c in contradictions if c["severity"] == "low"]

        logger.info(
            "Contradictions (after validation): %d total (%d high, %d med, %d low) — "
            "%d source-vs-source, %d source-vs-literature, %d intra-document",
            len(contradictions), len(high), len(med), len(low),
            len(svs), len(svl), len(intra),
        )

        return {
            "keywords": keywords,
            "sources_analysed": [s["source"] for s in grouped_sources],
            "pubmed_fetched": len(pubmed_results),
            "contradictions": contradictions,
            "source_vs_source": svs,
            "source_vs_literature": svl,
            "intra_document": intra,
            "severity_counts": {"high": len(high), "medium": len(med), "low": len(low)},
            "overall_assessment": report.overall_assessment,
        }
