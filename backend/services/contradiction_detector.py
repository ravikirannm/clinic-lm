from __future__ import annotations

import concurrent.futures
import json
import logging

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import ContradictionReport
from services.extract_keywords import ExtractKeywords
from services.notebook_rag import NotebookRAG

logger = logging.getLogger(__name__)

try:
    _extract_keywords = ExtractKeywords()
except Exception as e:
    logger.warning("NER model unavailable (%s); keyword extraction disabled", e)
    _extract_keywords = None

_SYSTEM = """\
You are a HYPER-CRITICAL CLINICAL DOCUMENT AUDITOR. Your only purpose is to find every \
logical inconsistency, clinical contradiction, and factual conflict hidden in patient \
documentation. You are NOT summarising — you are HUNTING for errors.

MINDSET
───────
You are suspicious of every sentence. You assume errors are present. A document that \
"looks fine" is one you have not scrutinised hard enough. Never give the benefit of the \
doubt. If two statements conflict logically or medically, it is a contradiction — flag it.

═══════════════════════════════════════════════════════
INTRA-DOCUMENT AUDIT  (contradictions WITHIN one document)
═══════════════════════════════════════════════════════
Run EVERY check below in order. Do not skip any.

1. LATERALITY — LEFT vs RIGHT
   Read every mention of "left" and "right" throughout the entire document.
   • Does the chief complaint / subjective name the same side as the physical exam?
   • Does the Assessment/Plan reference the same side as the exam findings?
   Example of contradiction: patient complains of LEFT knee injury → physical exam documents
   normal LEFT knee but swelling and positive tests on the RIGHT knee → Plan orders MRI of
   the LEFT knee. This is a critical charting error (wrong-site investigation risk).

2. FUNCTIONAL STATUS — SUBJECTIVE vs OBJECTIVE
   What does the patient say they can/cannot do?
   What did the clinician observe during the physical exam?
   These must be consistent. Conflicts are HIGH severity.
   Example: "completely unable to bear weight, using crutches" vs "ambulates into the exam
   room effortlessly without any assistive devices" → direct contradiction.

3. SYMPTOM DENIAL vs SYMPTOM DOCUMENTED
   Did the patient deny a symptom (numbness, pain, tingling, shortness of breath, etc.)?
   Does any other part of the document then describe that exact symptom as present?
   Example: "patient explicitly denies any numbness or tingling" vs "patient complains of
   notable paresthesias and pins-and-needles sensation" → HIGH severity.

4. MEDICATION HISTORY vs MEDICATION IN PLAN/ASSESSMENT
   Did the patient state they are taking NO medications / avoiding all drugs?
   Does the assessment or plan then mention a drug the patient is already taking?
   Example: "avoiding even over-the-counter painkillers to check baseline pain" vs
   "given that the patient has been taking Maximum Strength Tylenol 1000 mg q6h" → HIGH.

5. DIAGNOSIS/PLAN vs EXAM FINDINGS
   Does the primary diagnosis in the Assessment match what the physical exam actually found?
   Is the imaging/investigation ordered for the correct side and structure?
   Is equipment provided (e.g. crutches) consistent with the observed clinical state?

6. ALLERGY vs PRESCRIBED MEDICATION  (CRITICAL)
   Every documented allergy → scan ALL prescriptions for the same drug class:
   Penicillin allergy + amoxicillin / ampicillin / piperacillin = CRITICAL
   Sulfa allergy + TMP-SMX = CRITICAL
   NSAID allergy + ibuprofen / naproxen / aspirin = CRITICAL

7. DIAGNOSIS vs TREATMENT CORRECTNESS  (CRITICAL)
   Type 1 Diabetes Mellitus + Metformin only (no insulin) = CRITICAL error
   Active Peptic Ulcer Disease + any NSAID = CRITICAL contraindication

8. VITAL SIGNS vs CLINICAL LABELS
   Actual recorded value vs the clinical label applied to it:
   BP 112/70 called "hypertensive urgency" → grossly incorrect → HIGH
   "Regular sinus rhythm" documented + "Persistent Atrial Fibrillation" in history → flag it

9. DEMOGRAPHICS & HISTORY CONSISTENCY
   Gender in demographics vs pronouns/descriptors used elsewhere
   Age/DOB consistent across all references
   Symptom onset/duration stated identically wherever mentioned

═══════════════════════════════════════════════════════
SOURCE-VS-SOURCE AUDIT  (contradictions ACROSS different documents)
═══════════════════════════════════════════════════════
Only relevant when multiple documents are uploaded.
Find direct factual conflicts between one document and another:
• Different diagnoses for the same condition across documents
• Conflicting medication lists
• Conflicting allergy records
• Conflicting lab values or dates

═══════════════════════════════════════════════════════
DO NOT FLAG
═══════════════════════════════════════════════════════
• Information that elaborates or adds detail without contradicting
• Normal clinical nuance where context resolves the difference

═══════════════════════════════════════════════════════
SEVERITY
═══════════════════════════════════════════════════════
high   — wrong-site investigation/surgery risk, medication denial conflict, allergy-drug
         conflict, symptom denied then documented, patient said can't walk but walks fine,
         wrong drug class for disease
medium — meaningful clinical disagreement that would affect management
low    — minor wording inconsistency unlikely to cause patient harm

═══════════════════════════════════════════════════════
OUTPUT RULES
═══════════════════════════════════════════════════════
• Place INTRA-DOCUMENT findings in the `intra_document` array.
• Place CROSS-DOCUMENT findings in the `source_vs_source` array.
• NEVER describe a contradiction only in `overall_assessment` — anything written there
  and not in an array is INVISIBLE to the user. `overall_assessment` is a 1–2 sentence
  summary only.
• Use source names EXACTLY as they appear in the "UPLOADED DOCUMENTS" list.
• For `intra_document` items: source_a and source_b must be the SAME document name.
• For `source_vs_source` items: source_a and source_b must be DIFFERENT document names.
• Return ONLY valid JSON matching the schema. No commentary. No markdown.\
"""


def _retrieve_multi_topic(notebook_id: str, keywords: list[str], top_k: int = 8) -> list[dict]:
    """Parallel NotebookRAG queries on keyword subgroups."""
    if not keywords or not notebook_id:
        return []

    groups = [keywords[i:i + 3] for i in range(0, min(len(keywords), 12), 3)]
    queries = [" ".join(g) for g in groups if g]
    if not queries:
        return []

    def _fetch(q: str) -> list[dict]:
        try:
            return NotebookRAG.retrieve(notebook_id, q, top_k=top_k)
        except Exception as e:
            logger.warning("NotebookRAG failed for '%s': %s", q, e)
            return []

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(queries))) as ex:
        batches = list(ex.map(_fetch, queries))

    seen: set[str] = set()
    unique: list[dict] = []
    for batch in batches:
        for chunk in batch:
            key = chunk["content"][:80]
            if key not in seen:
                seen.add(key)
                unique.append(chunk)

    logger.info("ContradictionDetector: %d unique chunks from %d queries", len(unique), len(queries))
    return unique


def _group_by_source(chunks: list[dict]) -> list[dict]:
    """Group chunks by source name."""
    by_source: dict[str, list[str]] = {}
    for c in chunks:
        src = c.get("source", "Unknown source")
        by_source.setdefault(src, []).append(c["content"])
    return [{"source": src, "excerpts": excerpts} for src, excerpts in by_source.items()]


class ContradictionDetector:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def analyze(self, notebook_id: str, text: str) -> dict:
        # ── Step 1: NER keyword extraction ────────────────────────────────────
        keywords: list[str] = []
        if _extract_keywords is not None:
            try:
                keywords = _extract_keywords.get_clinical_ner_results(text)
            except Exception as e:
                logger.warning("Keyword extraction failed: %s", e)

        # ── Step 2: RAG retrieval from notebook ────────────────────────────────
        notebook_chunks = _retrieve_multi_topic(notebook_id, keywords, top_k=10)
        grouped = _group_by_source(notebook_chunks)
        uploaded_names = [g["source"] for g in grouped]

        logger.info("ContradictionDetector: %d chunks from %d sources", len(notebook_chunks), len(grouped))

        # Format chunk content for the prompt
        chunk_block = (
            "\n\n".join(f"[{c['source']}]\n{c['content']}" for c in notebook_chunks)
            if notebook_chunks else text[:6000]
        )

        fallback_note = (
            '(Document list is empty — use "Source Document" as source_a/source_b for intra_document items.)'
            if not uploaded_names else ""
        )

        cross_doc_note = (
            f"There are {len(uploaded_names)} uploaded documents — check for source_vs_source contradictions."
            if len(uploaded_names) > 1
            else "Only one document uploaded — leave source_vs_source empty."
        )

        user_prompt = f"""
UPLOADED DOCUMENTS — use these names EXACTLY for source_a and source_b:
{json.dumps(uploaded_names, indent=2)}
{fallback_note}

━━━ DOCUMENT TEXT TO AUDIT ━━━
{chunk_block}

━━━ CROSS-DOCUMENT NOTE ━━━
{cross_doc_note}

Now run the full mandatory checklist from your instructions against the text above.
Place every finding in `intra_document` or `source_vs_source`. Return only valid JSON.
"""

        # ── Step 3: LLM analysis ───────────────────────────────────────────────
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user",   "content": user_prompt},
                ],
                format=ContradictionReport.model_json_schema(),
                options={"temperature": 0.15},
            )
            report = ContradictionReport.model_validate_json(resp["message"]["content"])
            conf = max(0.0, min(1.0, report.confidence))
        except Exception as e:
            logger.error("Contradiction LLM call failed: %s", e)
            conf = 0.0
            report = ContradictionReport(overall_assessment="Analysis failed — LLM error.")

        # ── Step 4: Validate, normalise severity, tag with type ────────────────
        valid_sources = set(uploaded_names)
        _SEV = {"high": "high", "medium": "medium", "moderate": "medium", "low": "low"}

        def _normalise(item: dict) -> dict:
            item["severity"] = _SEV.get(item["severity"].lower(), "low")
            return item

        def _fix_intra(item: dict) -> dict | None:
            sa, sb = item["source_a"], item["source_b"]
            if sa != sb:
                logger.warning("intra_document: source_a != source_b ('%s'/'%s') — skipping", sa, sb)
                return None
            if sa not in valid_sources:
                if len(valid_sources) == 1:
                    canonical = next(iter(valid_sources))
                    item["source_a"] = item["source_b"] = canonical
                elif len(valid_sources) == 0:
                    pass  # keep LLM-assigned name
                else:
                    logger.warning("intra_document: '%s' not in uploaded set — skipping", sa)
                    return None
            return item

        def _fix_svs(item: dict) -> dict | None:
            sa, sb = item["source_a"], item["source_b"]
            if sa == sb:
                logger.warning("source_vs_source: same source on both sides ('%s') — skipping", sa)
                return None
            if sa not in valid_sources or sb not in valid_sources:
                logger.warning("source_vs_source: unknown source ('%s'/'%s') — skipping", sa, sb)
                return None
            return item

        intra: list[dict] = []
        for c in report.intra_document:
            item = _normalise(c.model_dump())
            item["type"] = "intra_document"
            fixed = _fix_intra(item)
            if fixed:
                intra.append(fixed)

        svs: list[dict] = []
        for c in report.source_vs_source:
            item = _normalise(c.model_dump())
            item["type"] = "source_vs_source"
            fixed = _fix_svs(item)
            if fixed:
                svs.append(fixed)

        contradictions = intra + svs
        high = [c for c in contradictions if c["severity"] == "high"]
        med  = [c for c in contradictions if c["severity"] == "medium"]
        low_ = [c for c in contradictions if c["severity"] == "low"]

        logger.info(
            "Contradictions: %d total (%d high, %d med, %d low) — %d intra, %d svs | conf=%.3f",
            len(contradictions), len(high), len(med), len(low_), len(intra), len(svs), conf,
        )

        return {
            "keywords": keywords,
            "sources_analysed": uploaded_names,
            "contradictions": contradictions,
            "intra_document": intra,
            "source_vs_source": svs,
            "severity_counts": {"high": len(high), "medium": len(med), "low": len(low_)},
            "overall_assessment": report.overall_assessment,
            "confidence": conf,
        }
