import hashlib
import json
import logging

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import Finding, FindingExtractionResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a clinical finding extractor. Your ONLY job is to map free text onto a
controlled vocabulary of finding ids supplied to you for this request. You do not
diagnose and you do not estimate probabilities — that is done by a separate
deterministic stage from your output.

For each finding id in the provided vocabulary, decide its status:
- "present": the text states or clearly implies the finding is present
- "absent": the text explicitly denies or rules out the finding
- "not_reported": the text says nothing about this finding either way

Only include a finding id in your output if its status is "present" or "absent" — omit
"not_reported" findings entirely rather than listing them. For every finding you include,
quote the exact verbatim span of the source text that supports it in source_span, and set
grade to a severity/qualifier if one is stated (e.g. "mild", "7/10", "3 days"), otherwise
null. Never invent a finding id that is not in the supplied vocabulary. Never assign a
posterior_likelihood, diagnosis, or condition — that is out of scope for this stage.

Output strict JSON only, matching the exact schema. No explanation. No preamble. No markdown.
"""

_PROMPT_VERSION_HASH = hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:12]


class FindingExtractor:
    """Stage 1 of the auditable pipeline: free text -> Finding[] against a controlled
    vocabulary (proposed fresh per request by services/finding_vocabulary.py, not
    fixed). Output feeds compute_posterior and is also snapshotted verbatim for replay
    — see docs/clinical_analyzer_refactor.md §9."""

    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def extract(self, text: str, vocabulary: list[str]) -> list[Finding]:
        if not vocabulary:
            return []
        user_prompt = f"""
        === CONTROLLED VOCABULARY (only use ids from this list) ===
        {json.dumps(vocabulary, indent=1)}

        === SOURCE TEXT ===
        {text}
        """
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                format=FindingExtractionResult.model_json_schema(),
                options={"temperature": 0},
            )
            result = FindingExtractionResult.model_validate_json(resp["message"]["content"])
        except Exception as e:
            logger.warning("Finding extraction failed: %s", e)
            return []

        extractor_version = f"{OLLAMA_MODEL}:findings:{_PROMPT_VERSION_HASH}"
        findings = [f for f in result.findings if f.name in vocabulary]
        dropped = len(result.findings) - len(findings)
        if dropped:
            logger.warning("Dropped %d finding(s) with names outside the controlled vocabulary", dropped)
        return [f.model_copy(update={"extractor_version": extractor_version}) for f in findings]
