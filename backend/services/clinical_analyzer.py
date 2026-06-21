import json
import logging

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

    def analyze(self, user_id: str, notebook_id: str, text: str) -> dict:
        # ── Step 1: keyword extraction ────────────────────────────────────────
        if _extract_keywords is not None:
            keywords = _extract_keywords.get_clinical_ner_results(text)
        else:
            keywords = []

        # ── Step 2: RAG retrieval ─────────────────────────────────────────────
        retrieved_docs: list = []
        if _rag_retriever is not None and keywords:
            try:
                retrieved_docs = _rag_retriever.retrieve(keywords)
            except Exception as e:
                logger.warning("RAG retrieval failed: %s", e)

        notebook_chunks: list = []
        if notebook_id and keywords:
            try:
                notebook_chunks = NotebookRAG.retrieve(notebook_id, " ".join(keywords))
            except Exception as e:
                logger.warning("NotebookRAG retrieval failed: %s", e)

        # ── Step 3: generate PubMed search queries ────────────────────────────
        system_prompt_pass_2 = (
            "You are a medical search query specialist. "
            "Your ONLY job is to generate optimized search queries for PubMed."
        )
        user_prompt_pass_2 = f"""
            === MEDICAL CONTEXT ===
            {text}

            === EXTRACTED KEYWORDS ===
            {json.dumps(keywords, indent=1)}

            === Extracted Medical Documents ===
            {json.dumps(retrieved_docs, indent=1)}

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
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt_pass_2},
                {"role": "user", "content": user_prompt_pass_2},
            ],
            format=PubMedSearchRequest.model_json_schema(),
            options={"temperature": 0.2},
        )
        medical_corpus_input = PubMedSearchRequest.model_validate_json(
            response["message"]["content"]
        )
        step_query_conf = max(0.0, min(1.0, medical_corpus_input.confidence))
        api_inputs = medical_corpus_input.model_dump()
        logger.info("Generated search queries: %s", api_inputs)

        # ── Step 4: PubMed fetch ──────────────────────────────────────────────
        pubmed_results = _pubmed_client.fetch_pubmed(api_inputs.get("pubmed", {}))

        # ── Step 5: clinical assessment ───────────────────────────────────────
        system_prompt_pass_3 = """
You are an expert clinical diagnostic assistant performing a structured differential diagnosis.
You will be given comprehensive medical information gathered from multiple authoritative sources.

Your job is to synthesize ALL inputs into a clear, evidence-based clinical assessment following
this strict reasoning pipeline:

STEP 1 — CONDITION IDENTIFICATION
Identify all plausible conditions consistent with the presented symptoms. Rank by likelihood.
Use ICD-11 codes. Never give a definitive diagnosis — always qualify as "possible" or "likely".

STEP 2 — SYMPTOM GAP ANALYSIS
For each condition shortlisted in Step 1, compare its canonical symptom profile against the
symptoms ALREADY reported. Identify hallmark symptoms NOT yet confirmed or denied.

STEP 3 — RED FLAGS & TESTS
Flag specific urgent warning signs with immediate actions.
Recommend targeted diagnostic tests with clear rationale.

Output strict JSON only. No explanation. No preamble. No markdown.
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

Based on ALL sources above, and following the STEP 1→3 reasoning pipeline, generate the
clinical assessment in this exact structure:

{{
    "possible_conditions": [
        {{
            "name": "condition name",
            "likelihood": "high | medium | low",
            "reasoning": "why this condition fits the currently reported symptoms",
            "supporting_evidence": "which source(s) support this",
            "unconfirmed_hallmark_symptoms": [
                "symptom A not yet reported",
                "symptom B not yet reported"
            ]
        }}
    ],
    "red_flags": [
        {{
            "symptom": "specific warning sign",
            "associated_condition": "condition this flag is tied to",
            "action": "what to do immediately"
        }}
    ],
    "recommended_tests": [
        {{
            "test": "test name",
            "reason": "what it rules in or out",
            "targets_condition": "condition this test helps confirm or exclude"
        }}
    ]
}}
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
        chat_prompt = f"""
You are an expert clinical diagnostic assistant.
You will be given a comprehensive medical analysis result.
Your job is to synthesize it into a clear, evidence-based response for a medical expert.
Keep language clear enough to understand, but do not dumb down the medical accuracy.
Use a professional, evidence-based tone.

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
