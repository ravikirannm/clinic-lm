from __future__ import annotations

import concurrent.futures
import json
import logging

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import PubMedSearchRequest, ConformanceAnalysis
from services.extract_keywords import ExtractKeywords
from services.notebook_rag import NotebookRAG
from external.pubmed import PubMedClient
from external.nlm_clinical import NLMClinicalClient

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
_nlm_client    = NLMClinicalClient()

_GUIDELINE_QUERY_SYSTEM = (
    "You are a medical search query specialist. "
    "Your ONLY job is to generate optimized PubMed queries "
    "specifically designed to retrieve official clinical practice guidelines."
)

_CONFORMANCE_SYSTEM = """\
You are a clinical guidelines conformance analyst. Your job is to compare a patient's \
current management against evidence-based clinical practice guidelines and identify deviations.

For each relevant guideline area found in the provided sources:
1. Identify what the guideline recommends for this patient's condition.
2. Determine whether the current management conforms, deviates, partially conforms, \
   or cannot be assessed from the available documentation.
3. For deviations, describe what is different and how severe it is.
4. Suggest the corrective action.

Severity definitions:
- major: deviation that could directly affect patient outcomes or safety
- minor: deviation from best practice but unlikely to cause immediate harm
- informational: FYI item, no urgent action required

Return ONLY a JSON object matching the schema. Be thorough — cover medications, \
dosing targets, monitoring intervals, and procedural recommendations.\
"""


class GuidelinesConformance:
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

        # ── Step 3: LLM generates guideline-optimised PubMed queries ─────────
        query_prompt = f"""
=== MEDICAL CONTEXT ===
{text}

=== EXTRACTED KEYWORDS ===
{json.dumps(keywords, indent=1)}

=== EXTRACTED DOCUMENTS ===
{json.dumps(retrieved_docs[:3], indent=1)}

=== YOUR TASK ===
Generate PubMed queries in strict JSON to find clinical practice guidelines.

{{
    "pubmed": {{
        "primary_query": "specific boolean query using MeSH terms for clinical guidelines",
        "fallback_query": "broader guideline query as fallback",
        "filters": ["Practice Guideline", "Guideline"]
    }}
}}

Rules:
- Queries MUST target official clinical practice guidelines, consensus statements, \
or evidence-based recommendations.
- Use AND/OR/NOT boolean operators and MeSH terms where possible.
- Do not diagnose. Only generate search queries.
"""
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _GUIDELINE_QUERY_SYSTEM},
                    {"role": "user", "content": query_prompt},
                ],
                format=PubMedSearchRequest.model_json_schema(),
                options={"temperature": 0.2},
            )
            api_inputs = PubMedSearchRequest.model_validate_json(
                resp["message"]["content"]
            ).model_dump()
        except Exception as e:
            logger.error("Guideline query generation failed: %s", e)
            api_inputs = {"pubmed": {"primary_query": " ".join(keywords[:4]) + " guideline"}}

        logger.info("Guidelines search queries: %s", api_inputs)

        # ── Step 4: Parallel fetch from all four guideline sources ───────────
        pubmed_query = api_inputs.get("pubmed", {})
        nlm_query    = " ".join(keywords[:4])
        books_query  = " ".join(keywords[:3]) + " clinical practice guideline"

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            pubmed_future  = ex.submit(_pubmed_client.fetch_pubmed,       pubmed_query, 10)
            books_future   = ex.submit(_pubmed_client.fetch_ncbi_books,   books_query,  4)
            medline_future = ex.submit(_nlm_client.fetch_guidelines,      nlm_query,    5)
            catalog_future = ex.submit(_nlm_client.search_nlm_catalog,    nlm_query,    3)

        pubmed_results   = pubmed_future.result()
        books_results    = books_future.result()
        medline_results  = medline_future.result()
        catalog_results  = catalog_future.result()

        all_guidelines = pubmed_results + books_results + medline_results + catalog_results
        logger.info(
            "Guidelines fetched — PubMed: %d, Bookshelf: %d, MedlinePlus: %d, NLM Catalog: %d",
            len(pubmed_results), len(books_results),
            len(medline_results), len(catalog_results),
        )

        if not all_guidelines:
            return {
                "keywords": keywords,
                "search_queries": api_inputs,
                "guidelines_fetched": 0,
                "findings": [],
                "deviations": [],
                "conforming": [],
                "not_assessed": [],
                "overall_summary": "No clinical guidelines could be retrieved for this presentation.",
            }

        # ── Step 5: LLM conformance analysis ─────────────────────────────────
        user_prompt = f"""
=== PATIENT DOCUMENTATION ===
{text}

=== PATIENT SOURCE DOCUMENTS (RAG) ===
{json.dumps(notebook_chunks, indent=1)}

=== CLINICAL GUIDELINES (PubMed + NCBI Bookshelf + NLM MedlinePlus + NLM Catalog) ===
{json.dumps(all_guidelines, indent=1)}

=== GENERAL MEDICAL KNOWLEDGE BASE ===
{json.dumps(retrieved_docs[:3], indent=1)}

Analyse each guideline area and compare against the patient's current management. \
Identify conforming practices and deviations. Return findings as structured JSON.
"""
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _CONFORMANCE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                format=ConformanceAnalysis.model_json_schema(),
                options={"temperature": 0.1},
            )
            analysis = ConformanceAnalysis.model_validate_json(resp["message"]["content"])
        except Exception as e:
            logger.error("Conformance analysis failed: %s", e)
            analysis = ConformanceAnalysis(findings=[], overall_summary="Analysis failed.")

        # Attach PMID/title from matched PubMed records where possible
        pmid_map = {r.get("id", ""): r for r in pubmed_results if r.get("id")}
        for finding in analysis.findings:
            if finding.pmid and finding.pmid in pmid_map:
                finding.guideline_title = pmid_map[finding.pmid].get("title")

        deviations = [f for f in analysis.findings if f.status in ("deviation", "partial")]
        conforming = [f for f in analysis.findings if f.status == "conforming"]
        not_assessed = [f for f in analysis.findings if f.status == "not_assessed"]

        logger.info(
            "Conformance: %d findings — %d deviations, %d conforming, %d not assessed",
            len(analysis.findings), len(deviations), len(conforming), len(not_assessed),
        )

        return {
            "keywords": keywords,
            "search_queries": api_inputs,
            "guidelines_fetched": len(all_guidelines),
            "sources": {
                "pubmed":     len(pubmed_results),
                "bookshelf":  len(books_results),
                "medlineplus": len(medline_results),
                "nlm_catalog": len(catalog_results),
            },
            "findings": [f.model_dump() for f in analysis.findings],
            "deviations": [f.model_dump() for f in deviations],
            "conforming": [f.model_dump() for f in conforming],
            "not_assessed": [f.model_dump() for f in not_assessed],
            "overall_summary": analysis.overall_summary,
        }
