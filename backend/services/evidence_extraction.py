"""Live evidence extraction — replaces a hardcoded LR/prior knowledge base with
extraction from the PubMed articles and RAG chunks already retrieved for THIS request.

No prior or LR value in the system is a source-code literal. Every number either comes
from a retrieved document, quoted verbatim and traced to its actual id, or it does not
exist in the output — a condition with no sourced prevalence statement in the retrieved
evidence gets no computed posterior at all, rather than a stand-in number.

Two independent guards against the LLM inventing a citation:
1. source_id must exactly match an id that was actually retrieved this request.
2. quote must appear (whitespace-normalized) verbatim inside that source's text.
Either failing drops the item — logged, not silently kept.
"""

import hashlib
import json
import logging
import re

import ollama

import pydantic

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.bayesian import LREntry, Prior
from services.data_model import EvidenceExtractionResult, ExtractedLR, ExtractedPrior

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are an evidence-extraction assistant. You will be given a list of candidate
conditions, a controlled vocabulary of finding ids, and a list of SOURCE DOCUMENTS
(PubMed abstracts and retrieved knowledge-base chunks), each with an id.

Your ONLY job is to find explicit numeric statements already present in the SOURCE
DOCUMENTS and structure them:

1. PRIOR: a baseline prevalence / base-rate for one of the candidate conditions in some
   population, e.g. "X% of patients presenting with chest pain had ACS".
2. LIKELIHOOD RATIO: a positive and/or negative likelihood ratio (LR+/LR-) for one of
   the controlled-vocabulary findings discriminating one of the candidate conditions.

Rules — read carefully, these are hard constraints, not preferences:
- Use ONLY numbers that are explicitly stated in the SOURCE DOCUMENTS text below. Do
  NOT use outside medical knowledge, even if you are confident it is correct.
- source_id must be copied EXACTLY from the id field of the document you took it from.
  Never invent an id, never reuse the same id for a claim that isn't actually in that
  document's text.
- quote must be a VERBATIM substring of that exact source's text — copy it exactly,
  do not paraphrase, do not summarize, do not combine two sentences.
- condition must be copied EXACTLY as given in the candidate conditions list.
- finding must be copied EXACTLY as given in the controlled vocabulary list.
- If no source document contains a usable number for a given condition or
  finding/condition pair, do NOT include it. An empty priors/lr_entries list is the
  correct output when the retrieved documents simply don't contain this information —
  it is far better than a fabricated number with a plausible-looking citation.
- probability MUST be a fraction between 0 and 1, never a percentage. If the source
  states "5.1%", output 0.051, not 5.1.
- stratum is required for a prior: name the specific population the number describes
  (e.g. "adult ED patients presenting with chest pain"), not a blank or generic string.
- grade must honestly classify what kind of study the source is (systematic_review,
  rct, cohort_study, case_control, case_report, expert_consensus, or patient_reported)
  based on its title/abstract — do not default to the same grade for every source; a
  case report and a meta-analysis are not the same evidence grade.

Output strict JSON only, matching the exact schema. No explanation. No preamble. No markdown.
"""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _quote_verified(quote: str, source_text: str) -> bool:
    q = _normalize(quote)
    # 8 chars is not a principled cutoff — it just rejects trivially short/empty quotes
    # (e.g. a stray "the") that would trivially match almost any source and defeat the
    # point of requiring a verbatim quote at all.
    return bool(q) and len(q) >= 8 and q in _normalize(source_text)


class EvidenceExtractor:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def extract(self, candidate_conditions: list[str], finding_vocabulary: list[str],
                pubmed_results: list[dict], retrieved_docs: list[dict]) -> tuple[list[Prior], list[LREntry]]:
        sources: list[dict] = []
        for r in pubmed_results:
            pmid = r.get("id")
            if not pmid:
                continue
            sources.append({"id": str(pmid), "text": f"{r.get('title', '')}\n{r.get('abstract', '')}"})
        for i, d in enumerate(retrieved_docs):
            sources.append({"id": f"rag:{d.get('source', 'unknown')}:{i}", "text": d.get("content", "")})

        if not sources or not candidate_conditions:
            return [], []

        user_prompt = f"""
        === CANDIDATE CONDITIONS ===
        {json.dumps(candidate_conditions, indent=1)}

        === CONTROLLED FINDING VOCABULARY ===
        {json.dumps(finding_vocabulary, indent=1)}

        === SOURCE DOCUMENTS ===
        {json.dumps(sources, indent=1)}
        """
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                format=EvidenceExtractionResult.model_json_schema(),
                options={"temperature": 0},
            )
            raw = json.loads(resp["message"]["content"])
        except Exception as e:
            logger.warning("Evidence extraction call/JSON-parse failed: %s", e)
            return [], []

        # Validate each item independently rather than the whole payload at once —
        # one malformed item (e.g. a percentage instead of a fraction) must not
        # discard every other, correctly-formed extraction in the same response.
        extracted_priors: list[ExtractedPrior] = []
        for item in raw.get("priors", []):
            try:
                extracted_priors.append(ExtractedPrior.model_validate(item))
            except pydantic.ValidationError as e:
                logger.warning("Dropping malformed extracted prior %r: %s", item, e)

        extracted_lr_entries: list[ExtractedLR] = []
        for item in raw.get("lr_entries", []):
            try:
                extracted_lr_entries.append(ExtractedLR.model_validate(item))
            except pydantic.ValidationError as e:
                logger.warning("Dropping malformed extracted LR entry %r: %s", item, e)

        result = EvidenceExtractionResult(priors=extracted_priors, lr_entries=extracted_lr_entries)

        by_id = {s["id"]: s["text"] for s in sources}
        kb_version = "live_extraction:" + hashlib.sha256(
            json.dumps(sources, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]

        priors: list[Prior] = []
        for p in result.priors:
            src_text = by_id.get(p.source_id)
            if src_text is None:
                logger.warning("Dropping prior for %r: source_id %r not in retrieved documents", p.condition, p.source_id)
                continue
            if p.condition not in candidate_conditions:
                logger.warning("Dropping prior: condition %r not in candidate list", p.condition)
                continue
            if not _quote_verified(p.quote, src_text):
                logger.warning("Dropping prior for %r: quote not found verbatim in source %r", p.condition, p.source_id)
                continue
            priors.append(Prior(condition=p.condition, probability=p.probability, source_id=p.source_id,
                                 stratum=p.stratum, kb_version=kb_version, grade=p.grade))

        lr_entries: list[LREntry] = []
        for e in result.lr_entries:
            src_text = by_id.get(e.source_id)
            if src_text is None:
                logger.warning("Dropping LR for (%r, %r): source_id %r not in retrieved documents",
                                e.finding, e.condition, e.source_id)
                continue
            if e.condition not in candidate_conditions or e.finding not in finding_vocabulary:
                logger.warning("Dropping LR for (%r, %r): not in candidate/vocabulary lists", e.finding, e.condition)
                continue
            if not _quote_verified(e.quote, src_text):
                logger.warning("Dropping LR for (%r, %r): quote not found verbatim in source %r",
                                e.finding, e.condition, e.source_id)
                continue
            lr_entries.append(LREntry(finding=e.finding, condition=e.condition,
                                       lr_present=e.lr_present, lr_absent=e.lr_absent,
                                       source_id=e.source_id, grade=e.grade,
                                       kb_version=kb_version))

        return priors, lr_entries
