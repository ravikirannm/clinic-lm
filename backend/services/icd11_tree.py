import concurrent.futures
import json
import logging

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import ICD11SearchRequest
from services.extract_keywords import ExtractKeywords
from services.notebook_rag import NotebookRAG
from external.icd11 import ICD11Client

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

_icd11_client = ICD11Client()


class ICD11TreeService:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def generate_icd11_tree(self, text: str, notebook_id: str = "") -> dict:
        # ── Step 1: keyword extraction ────────────────────────────────────────
        keywords = _extract_keywords.get_clinical_ner_results(text) if _extract_keywords else []

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

        # ── Step 3: LLM generates ICD-11 search terms ────────────────────────
        system_prompt = (
            "You are a medical coding specialist. "
            "Your ONLY job is to generate ICD-11 disease name search terms."
        )
        user_prompt = f"""
            === MEDICAL CONTEXT ===
            {text}

            === EXTRACTED KEYWORDS ===
            {json.dumps(keywords, indent=1)}

            === PATIENT SOURCE DOCUMENTS ===
            {json.dumps(notebook_chunks, indent=1)}

            === RETRIEVED MEDICAL DOCUMENTS ===
            {json.dumps(retrieved_docs, indent=1)}

            === YOUR TASK ===
            Generate 5 to 10 ICD-11 standard disease names to search.
            Output strict JSON only. No explanation. No preamble. No markdown.

            {{
                "search_terms": [
                    "standard disease name 1",
                    "standard disease name 2",
                    "standard disease name 3",
                    "standard disease name 4",
                    "standard disease name 5",
                ]
            }}

            Rules:
            - Use standard ICD-11 disease names, not symptom descriptions
            - Do not diagnose — only generate search terms
            - Prefer specific conditions over broad categories
        """
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format=ICD11SearchRequest.model_json_schema(),
            options={"temperature": 0.2},
        )
        search_request = ICD11SearchRequest.model_validate_json(response["message"]["content"])
        search_terms = search_request.search_terms
        logger.info("ICD-11 search terms: %s", search_terms)

        # ── Step 4: ICD-11 search via NLM ────────────────────────────────────
        icd11_results = _icd11_client.fetch_icd11(search_terms)
        logger.info("ICD-11 results: %d matches", len(icd11_results))

        # ── Step 5: Build WHO trees in parallel ───────────────────────────────
        def _build(item: dict) -> dict | None:
            try:
                return _icd11_client.build_tree(item["code"], item.get("title", ""))
            except Exception as e:
                logger.warning("Tree build failed for %s: %s", item["code"], e)
                return None

        if icd11_results:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                trees = list(ex.map(_build, icd11_results))
            for item, tree in zip(icd11_results, trees):
                item["tree"] = tree

        return {
            "keywords": keywords,
            "search_terms": search_terms,
            "icd11_results": icd11_results,
        }
