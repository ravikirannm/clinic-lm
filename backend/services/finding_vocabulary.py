"""Dynamic finding vocabulary — replaces a fixed, domain-specific list (e.g. a
chest-pain-only set baked into source code) with an LLM-proposed set of canonical
finding ids derived from THIS patient's presenting text, fresh every request.

Nothing here is a clinical claim about prevalence or likelihood — it's a per-request
naming scheme so a Finding.name produced by services/finding_extraction.py can be
joined against an LREntry.finding produced by services/evidence_extraction.py within
the same request. Since the LR knowledge base is now also extracted live per request
(not accumulated in a persistent table), there is no cross-request consistency
requirement that would demand a fixed vocabulary — each request is self-contained.
"""

import logging

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import FindingVocabularyProposal

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a clinical vocabulary assistant. Read the patient presentation and propose a
controlled vocabulary of canonical finding ids: discrete, checkable clinical
observations (symptoms, signs, risk factors, relevant history) useful for
differentiating the conditions this presentation could represent.

Rules:
- Each id must be lowercase snake_case, e.g. "chest_pain_pleuritic", "recent_surgery".
- One discrete observation per id — not a diagnosis, not a numeric value, not a sentence.
- Include findings actually mentioned in the text AND clinically relevant findings that
  would help discriminate between likely conditions but are NOT yet mentioned — these
  are exactly the findings worth asking about next.
- Propose 10-30 ids. Deduplicate.

Output strict JSON only, matching the exact schema. No explanation. No preamble. No markdown.
"""


class FindingVocabularyProposer:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def propose(self, text: str) -> list[str]:
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
                format=FindingVocabularyProposal.model_json_schema(),
                options={"temperature": 0},
            )
            result = FindingVocabularyProposal.model_validate_json(resp["message"]["content"])
        except Exception as e:
            logger.warning("Finding vocabulary proposal failed: %s", e)
            return []

        ids: list[str] = []
        seen: set[str] = set()
        for fid in result.finding_ids:
            norm = fid.strip().lower().replace(" ", "_").replace("-", "_")
            if norm and norm not in seen:
                seen.add(norm)
                ids.append(norm)
        return ids
