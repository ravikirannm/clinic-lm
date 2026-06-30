import concurrent.futures
import json
import logging

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import PubMedSearchRequest, ArticleGrading
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

_STUDY_TYPE_MAP = [
    (["Meta-Analysis", "Systematic Review"],             "Meta-Analysis / Systematic Review", "high"),
    (["Randomized Controlled Trial"],                    "Randomized Controlled Trial",        "high"),
    (["Controlled Clinical Trial", "Clinical Trial"],    "Clinical Trial",                     "moderate"),
    (["Review"],                                         "Review",                             "moderate"),
    (["Observational Study", "Cohort Study"],            "Observational Study",                "low-moderate"),
    (["Case Reports"],                                   "Case Report",                        "low"),
    (["Letter", "Editorial", "Comment"],                 "Letter / Editorial",                 "very-low"),
]

_GRADE_LETTER = {
    "high": "A",
    "moderate": "B",
    "low-moderate": "C",
    "low": "C",
    "very-low": "D",
}

_GRADING_SYSTEM = (
    "You are a medical evidence appraiser. Given an article title and abstract, extract:\n"
    "1. sample_size: the number of participants/patients as an integer, or null if not stated.\n"
    "2. bias_flags: a list of short methodological concern phrases found in the text "
    "(e.g. 'Retrospective design', 'Single-centre study', 'No control group', "
    "'Open-label design', 'Self-reported outcomes', 'Pilot study', 'Non-randomized', "
    "'Potential conflict of interest'). Only include flags with clear evidence in the text. "
    "Return an empty list if none apply.\n"
    "3. summary: a concise 2-3 sentence plain-language summary of what the study did, "
    "its key findings, and clinical relevance. Be specific and factual."
)


class LiteratureReviewService:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def _grade_single(self, article: dict) -> dict:
        pub_types: list = article.get("pub_types", [])

        # Study type and evidence level from structured PubMed publication types
        study_type = "Journal Article"
        evidence_level = "low"
        for keywords, label, level in _STUDY_TYPE_MAP:
            if any(k in pt for k in keywords for pt in pub_types):
                study_type = label
                evidence_level = level
                break

        grade = _GRADE_LETTER.get(evidence_level, "D")

        # LLM extracts sample size and bias flags from the abstract
        abstract = article.get("abstract", "") or ""
        title = article.get("title", "") or ""
        sample_size = None
        bias_flags: list[str] = []
        summary = ""

        if abstract and abstract != "No abstract available.":
            try:
                response = self.client.chat(
                    model=OLLAMA_MODEL,
                    messages=[
                        {"role": "system", "content": _GRADING_SYSTEM},
                        {"role": "user", "content": f"Title: {title}\n\nAbstract: {abstract[:1200]}"},
                    ],
                    format=ArticleGrading.model_json_schema(),
                    options={"temperature": 0},
                )
                grading = ArticleGrading.model_validate_json(response["message"]["content"])
                sample_size = grading.sample_size
                bias_flags = grading.bias_flags
                summary = grading.summary or ""
            except Exception as e:
                logger.warning("LLM grading failed for PMID %s: %s", article.get("id"), e)

        return {
            **article,
            "study_type": study_type,
            "evidence_level": evidence_level,
            "grade": grade,
            "sample_size": sample_size,
            "bias_flags": bias_flags,
            "summary": summary,
        }

    def analyze(self, user_id: str, notebook_id: str, text: str, on_progress=None) -> dict:
        def _progress(step: str, pct: int):
            if on_progress:
                on_progress(step, pct)

        # ── Step 1: keyword extraction ────────────────────────────────────────
        _progress("Extracting clinical keywords…", 10)
        keywords = _extract_keywords.get_clinical_ner_results(text) if _extract_keywords else []

        # ── Step 2: RAG retrieval ─────────────────────────────────────────────
        _progress("Retrieving medical knowledge base…", 25)
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
        _progress("Generating PubMed search queries…", 45)
        system_prompt = (
            "You are a medical search query specialist. "
            "Your ONLY job is to generate optimized search queries for PubMed."
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
            Generate search queries in strict JSON only. No explanation. No preamble. No markdown.

            {{
                "pubmed": {{
                    "primary_query": "most specific boolean query using MeSH terms",
                    "fallback_query": "broader query if primary returns nothing",
                    "filters": ["Journal Article", "Review", "Clinical Trial"]
                }}
            }}

            Rules:
            - Use AND/OR/NOT boolean operators
            - Use MeSH terms where possible e.g. [MeSH Terms]
            - Do not diagnose, only generate search queries
        """
        response = self.client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format=PubMedSearchRequest.model_json_schema(),
            options={"temperature": 0.2},
        )
        search_request = PubMedSearchRequest.model_validate_json(response["message"]["content"])
        search_queries = search_request.model_dump()
        logger.info("Literature review search queries: %s", search_queries)

        # ── Step 4: PubMed fetch ──────────────────────────────────────────────
        _progress("Fetching PubMed articles…", 60)
        raw_articles = _pubmed_client.fetch_pubmed(search_queries.get("pubmed", {}), 20)
        valid = [a for a in raw_articles if not a.get("error")]
        logger.info("PubMed returned %d articles", len(valid))

        # ── Step 5: LLM-based GRADE grading (parallel) ───────────────────────
        _progress("Grading article evidence quality…", 78)
        articles: list[dict] = []
        if valid:
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                articles = list(ex.map(self._grade_single, valid))

        return {
            "keywords": keywords,
            "search_queries": search_queries,
            "articles": articles,
        }
