from __future__ import annotations

import json
import logging
from collections.abc import Generator

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import PubMedSearchRequest
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

_SYSTEM_BASE = """\
You are an advanced clinical decision support AI designed to assist physicians and \
medical experts with structured differential diagnosis (DDx) and clinical reasoning.

### CORE PIPELINE (Execute silently, output conversationally)

STEP 1 — CONDITION IDENTIFICATION (DIFFERENTIAL DIAGNOSIS)
Prioritised differential diagnosis based on the clinical presentation and provided data.
Present top differentials concisely. Include ICD-11 codes where relevant.

STEP 2 — SYMPTOM GAP ANALYSIS & CLINICAL PROBING
Compare the clinical presentation against hallmark signs. Propose 1–2 targeted questions \
to help rule in or rule out differentials.

STEP 3 — RED FLAGS & DIAGNOSTIC WORKUP
Flag acute deterioration indicators immediately. Suggest high-yield diagnostics with \
evidence-based rationale.

### TONE
- Peer-to-peer clinical professionalism — concise, scannable, bullet-pointed.
- Use precise medical terminology. Respect the clinician's expertise.
- Always use probabilistic language ("consistent with", "high suspicion for").
- If imminent threat to life, prioritise stabilisation over differentials.
- Format responses in clean Markdown (headers, bullets, bold key terms).
"""


class ChatBot:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    # ── Context builder (called once per chat message) ────────────────────────

    def _build_context(
        self,
        notebook_id: str,
        documentation: str,
        user_query: str,
    ) -> tuple[list, list]:
        """Return (retrieved_docs, notebook_chunks) for the system prompt."""
        keywords: list[str] = []
        if _extract_keywords is not None:
            try:
                keywords = _extract_keywords.get_clinical_ner_results(
                    f"{documentation[:1000]} {user_query}"
                )
            except Exception as e:
                logger.warning("Keyword extraction failed: %s", e)

        retrieved_docs: list = []
        if _rag_retriever is not None and keywords:
            try:
                retrieved_docs = _rag_retriever.retrieve(keywords)
            except Exception as e:
                logger.warning("RAG retrieval failed: %s", e)

        notebook_chunks: list = []
        if notebook_id and keywords:
            try:
                notebook_chunks = NotebookRAG.retrieve(
                    notebook_id, " ".join(keywords), top_k=6
                )
            except Exception as e:
                logger.warning("NotebookRAG retrieval failed: %s", e)

        return retrieved_docs, notebook_chunks

    def _build_pubmed(self, documentation: str, keywords: list[str]) -> list:
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a medical search query specialist. "
                            "Generate optimised PubMed search queries only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"=== MEDICAL CONTEXT ===\n{documentation[:2000]}\n\n"
                            f"=== KEYWORDS ===\n{json.dumps(keywords)}\n\n"
                            "Generate PubMed queries in strict JSON."
                        ),
                    },
                ],
                format=PubMedSearchRequest.model_json_schema(),
                options={"temperature": 0.2},
            )
            api_inputs = PubMedSearchRequest.model_validate_json(
                resp["message"]["content"]
            ).model_dump()
            return _pubmed_client.fetch_pubmed(api_inputs.get("pubmed", {}))
        except Exception as e:
            logger.warning("PubMed query failed: %s", e)
            return []

    # ── Streaming chat ────────────────────────────────────────────────────────

    def stream(
        self,
        notebook_id: str,
        documentation: str,
        history: list[dict],
        user_query: str,
    ) -> Generator[str, None, None]:
        """
        Yield SSE-formatted strings:  data: {"content": "..."}\n\n
        Last chunk:                   data: [DONE]\n\n
        """
        retrieved_docs, notebook_chunks = self._build_context(
            notebook_id, documentation, user_query
        )

        # Build keywords for PubMed only on first turn to save time
        keywords: list[str] = []
        if _extract_keywords is not None:
            try:
                keywords = _extract_keywords.get_clinical_ner_results(
                    f"{documentation[:1000]} {user_query}"
                )
            except Exception:
                pass

        pubmed_results = self._build_pubmed(documentation, keywords)

        system_prompt = (
            _SYSTEM_BASE
            + f"\n=== PATIENT DOCUMENTATION ===\n{documentation[:3000]}\n"
            + f"\n=== PATIENT SOURCE DOCUMENTS (RAG) ===\n{json.dumps(notebook_chunks, indent=1)}\n"
            + f"\n=== MEDICAL KNOWLEDGE BASE ===\n{json.dumps(retrieved_docs, indent=1)}\n"
            + f"\n=== PUBMED EVIDENCE ===\n{json.dumps(pubmed_results, indent=1)}\n"
        )

        messages = [{"role": "system", "content": system_prompt}]
        # Inject conversation history (user/assistant turns only)
        for msg in history:
            if msg.get("role") in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_query})

        try:
            for chunk in self.client.chat(
                model=OLLAMA_MODEL,
                messages=messages,
                stream=True,
                options={"temperature": 0.3},
            ):
                content = chunk.get("message", {}).get("content", "")
                if content:
                    yield f"data: {json.dumps({'content': content})}\n\n"
        except Exception as e:
            logger.error("Chat stream error: %s", e)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

        yield "data: [DONE]\n\n"
