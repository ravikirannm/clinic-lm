import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import PubMedSearchRequest, ClinicalAssessment
from services.extract_keywords import ExtractKeywords
from services.notebook_rag import NotebookRAG
from external.pubmed import PubMedClient

logger = logging.getLogger(__name__)

# Heavy initializations — fail gracefully if models aren't downloaded yet
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


class ClinicalAnalyzer:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def analyze(self, user_id: str, notebook_id: str, text: str, on_progress=None) -> dict:
        def _progress(step: str, pct: int):
            if on_progress:
                on_progress(step, pct)

        # ── Step 1: keyword extraction ────────────────────────────────────────
        _progress("Extracting clinical keywords…", 10)
        if _extract_keywords is not None:
            keywords = _extract_keywords.get_clinical_ner_results(text)
        else:
            keywords = []

        # ── Steps 2+3: RAG retrievals and PubMed query generation in parallel ──
        _progress("Retrieving medical knowledge base…", 25)
        # All three tasks only need `keywords` and `text` from Step 1; they are
        # independent of each other so we run them concurrently.
        retrieved_docs: list = []
        notebook_chunks: list = []
        medical_corpus_input = None
        api_inputs: dict = {}

        def _fetch_medical_rag():
            if _rag_retriever is not None and keywords:
                try:
                    return _rag_retriever.retrieve(keywords)
                except Exception as e:
                    logger.warning("RAG retrieval failed: %s", e)
            return []

        def _fetch_notebook_rag():
            if notebook_id and keywords:
                try:
                    return NotebookRAG.retrieve(notebook_id, " ".join(keywords))
                except Exception as e:
                    logger.warning("NotebookRAG retrieval failed: %s", e)
            return []

        def _generate_pubmed_queries():
            system_prompt_pass_2 = (
                "You are a medical search query specialist. "
                "Your ONLY job is to generate optimized search queries for PubMed."
            )
            user_prompt_pass_2 = f"""
            === MEDICAL CONTEXT ===
            {text}

            === EXTRACTED KEYWORDS ===
            {json.dumps(keywords, indent=1)}

            === YOUR TASK ===
            Generate search queries in strict JSON only. No explanation. No preamble. No markdown.

            {{
                "pubmed": {{
                    "primary_query": "most specific boolean query using MeSH terms",
                    "fallback_query": "broader query if primary returns nothing",
                    "filters": ["Journal Article", "Review", "Clinical Trial"]
                }}
            }}

            Rules:
            - PubMed primary query must use AND/OR/NOT boolean operators
            - PubMed must use MeSH terms where possible e.g. [MeSH Terms]
            - Do not diagnose, only generate search queries
            """
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt_pass_2},
                    {"role": "user", "content": user_prompt_pass_2},
                ],
                format=PubMedSearchRequest.model_json_schema(),
                options={"temperature": 0.2},
            )
            return PubMedSearchRequest.model_validate_json(resp["message"]["content"])

        with ThreadPoolExecutor(max_workers=3) as pool:
            fut_medical = pool.submit(_fetch_medical_rag)
            fut_notebook = pool.submit(_fetch_notebook_rag)
            fut_queries = pool.submit(_generate_pubmed_queries)

            retrieved_docs = fut_medical.result()
            notebook_chunks = fut_notebook.result()
            medical_corpus_input = fut_queries.result()

        step_query_conf = max(0.0, min(1.0, medical_corpus_input.confidence))
        api_inputs = medical_corpus_input.model_dump()
        logger.info("Generated search queries: %s", api_inputs)

        # ── Step 4: PubMed fetch ──────────────────────────────────────────────
        _progress("Fetching PubMed evidence…", 45)
        pubmed_results = _pubmed_client.fetch_pubmed(api_inputs.get("pubmed", {}))

        # ── Step 5: clinical assessment ───────────────────────────────────────
        _progress("Performing clinical assessment…", 62)
        system_prompt_pass_3 = """
You are an expert clinical diagnostic assistant performing a structured Bayesian differential diagnosis.
You will be given comprehensive medical information gathered from multiple authoritative sources.

Follow this reasoning pipeline exactly. Do not skip steps. Do not collapse steps into the final
output without doing the reasoning first.

STEP 0 — EPIDEMIOLOGICAL PRIOR
Before touching symptoms, state the baseline prevalence/base-rate for each candidate condition given
the patient's known demographics (age, sex, region, relevant history). If demographics are missing,
say so and use general population priors. This prior is set BEFORE symptom-matching to avoid anchoring
directly on the presenting complaint.

STEP 1 — BAYESIAN UPDATE (CONDITION IDENTIFICATION)
For each candidate condition, walk through how the reported symptoms shift the prior toward a posterior:
which symptoms increase likelihood, which decrease it, which are non-discriminating. State the resulting
posterior as high/medium/low/very_low — never as a definitive diagnosis. Use ICD-11 codes.

STEP 2 — ACTIVE FALSIFICATION
For every condition in Step 1, you must identify at least one piece of evidence AGAINST it, even if weak.
If the available sources contain no disconfirming evidence, state that explicitly rather than omitting it.
This step exists specifically to counter confirmation/anchoring bias — do not skip it for the leading diagnosis.

STEP 3 — SYMPTOM GAP ANALYSIS
For each condition, compare its canonical symptom profile against symptoms ALREADY reported. List hallmark
symptoms NOT yet confirmed or denied.

STEP 4 — NEXT BEST DISCRIMINATOR
Across all shortlisted conditions, identify the SINGLE question or test that would most reduce uncertainty
between the top two differentials — i.e., the one with the highest information gain, not just any test that
helps any one condition. Justify why it beats the alternatives.

STEP 5 — RED FLAGS & TESTS
Flag urgent warning signs with immediate actions, citing a named clinical decision rule (e.g. CURB-65, Wells
Score, NEWS2) where one genuinely applies — do not invent a rule that doesn't exist. For each recommended
test, state what a positive vs. negative result does to the probability of the targeted condition, and assign
a priority (stat/urgent/routine).

EVIDENCE HIERARCHY
When sources conflict, weight them: systematic review > RCT > cohort study > case-control > case report >
expert consensus > patient-reported. Tag every piece of evidence with its source type, a specific source_id
(PMID, RAG chunk id, or document name — never vague), and its evidence grade.

HEDGING REQUIREMENT
Never state a definitive diagnosis. Use "possible," "likely," "cannot be confirmed without X." This is a
decision-support tool for a clinician, not an autonomous diagnostic authority.

Output strict JSON only, matching the exact schema. No field may be omitted — if a value would be empty,
state that explicitly inside the field rather than leaving it out. No explanation. No preamble. No markdown.
"""
        user_prompt_pass_3 = f"""
=== PATIENT SYMPTOM VARIANTS & KEYWORDS ===
{json.dumps(keywords, indent=1)}

=== PATIENT SOURCE DOCUMENTS ===
{json.dumps(notebook_chunks, indent=1)}

=== MEDICAL KNOWLEDGE BASE (RAG) ===
{json.dumps(retrieved_docs, indent=1)}

=== PUBMED EVIDENCE ===
{json.dumps(pubmed_results, indent=1)}

Based on ALL sources above, and following the STEP 0→5 reasoning pipeline, generate the clinical
assessment matching the provided schema exactly. Every condition must include a non-empty
epidemiological_prior, likelihood_rationale, supporting_evidence, and refuting_evidence. The
next_best_discriminator must reference the actual top differentials you identified, not a generic test.
"""
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt_pass_3},
                {"role": "user", "content": user_prompt_pass_3},
            ],
            format=ClinicalAssessment.model_json_schema(),
            options={"temperature": 0},
        )
        assessment_obj = ClinicalAssessment.model_validate_json(response["message"]["content"])
        step_assessment_conf = max(0.0, min(1.0, assessment_obj.confidence))
        symptom_analysis = assessment_obj.model_dump()

        total_confidence = round(step_query_conf * step_assessment_conf, 3)

        response_data = {
            "keywords": keywords,
            "generated_queries": api_inputs,
            "pubmed_results": pubmed_results,
            "symptom_analysis": symptom_analysis,
            "confidence": total_confidence,
        }

        # ── Step 6: human-readable summary ───────────────────────────────────
        _progress("Generating clinical summary…", 88)
        chat_prompt = f"""
You are an expert clinical diagnostic assistant. You will be given a comprehensive medical analysis
result that already encodes Bayesian reasoning (priors, posteriors, supporting and refuting evidence).
Synthesize it into a clear, evidence-based response for a medical expert. Surface the epidemiological
prior and the next_best_discriminator explicitly — these are the most actionable parts of the analysis.
Keep language clear enough to understand, but do not dumb down the medical accuracy. Do not soften the
hedged language into anything definitive.

Latest analysis result:
{json.dumps(response_data, indent=1)}

Please generate a concise but thorough explanation of the clinical findings.
"""
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": chat_prompt},
                {"role": "user", "content": text},
            ],
            stream=False,
            options={"temperature": 0.4},
        )
        response_data["query_response"] = response["message"]["content"]

        return response_data
