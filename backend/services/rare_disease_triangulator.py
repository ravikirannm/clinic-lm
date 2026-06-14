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


class RareDiseaseTriangulator:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def analyze(self, user_id: str, notebook_id: str, text: str) -> dict:
        # ── Step 1: keyword extraction ────────────────────────────────────────
        if _extract_keywords is not None:
            keywords = _extract_keywords.get_clinical_ner_results(text)
        else:
            keywords = []

        # ── Step 2 (optional): RAG retrieval ─────────────────────────────────
        retrieved_docs: list = []
        if _rag_retriever is not None and keywords:
            try:
                retrieved_docs = _rag_retriever.retrieve(keywords)
            except Exception as e:
                logger.warning("RAG retrieval failed: %s", e)

        if notebook_id and keywords:
            try:
                notebook_chunks = NotebookRAG.retrieve(notebook_id, " ".join(keywords))
            except Exception as e:
                logger.warning("NotebookRAG retrieval failed: %s", e)

        # ── Step 5: clinical assessment ───────────────────────────────────────
        system_prompt_pass_3 = """
You are an expert clinical data extractor specializing in identifying phenotypic abnormalities from medical text.
Your job is to analyze the provided patient records and extract all raw symptoms, clinical signs, and physical findings.

Guidelines:
1. Extract the raw symptom text representing a clinical phenotype.
2. Keep terms concise and atomic (e.g., "muscle weakness", "drooping eyelid", "scoliosis") to optimize them for search in the Human Phenotype Ontology (HPO).
3. Do not extract diagnoses, medications, or test names—only the physical symptoms and phenotypic traits experienced by the patient.
4. Output strict JSON only. No explanation. No preamble. No markdown blocks.
"""

        user_prompt_pass_3 = f"""
=== PATIENT SYMPTOM VARIANTS & KEYWORDS ===
{json.dumps(keywords, indent=1)}

=== PATIENT SOURCE DOCUMENTS ===
{json.dumps(notebook_chunks, indent=1)}

=== MEDICAL KNOWLEDGE BASE (RAG) ===
{json.dumps(retrieved_docs, indent=1)}

Based on ALL sources above, extract all distinct, currently present symptoms and signs. Generate the output in this exact JSON structure:

{{
    "extracted_symptoms": [
        "short symptom phrase 1",
        "short symptom phrase 2",
        "short symptom phrase 3"
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
        symptom_analysis = ClinicalAssessment.model_validate_json(
            response["message"]["content"]
        ).model_dump()

