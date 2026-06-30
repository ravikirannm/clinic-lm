from __future__ import annotations

import concurrent.futures
import logging
from datetime import datetime, timezone

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

DOCUMENT_TYPES: dict[str, str] = {
    "referral_letter":   "Referral Letter",
    "discharge_summary": "Discharge Summary",
    "case_writeup":      "Case Write-up",
}

_SYSTEM_PROMPTS: dict[str, str] = {
    "referral_letter": """\
You are an experienced clinician drafting a formal referral letter to a specialist.
Write a professional referral letter based on the patient documentation provided.

The letter must include:
- Date (today) and formal heading
- Patient demographics (name, age, gender, DOB if available)
- Reason for referral (clearly stated in the opening paragraph)
- Relevant clinical history and presenting complaint
- Pertinent examination findings
- Current medications and known allergies
- Relevant investigation results (labs, imaging, ECG, etc.)
- Urgency level (Routine / Soon / Urgent / Emergency)
- Specific questions or actions requested from the specialist
- Closing remarks and referring clinician block (use "[Dr. Name, Specialty, Contact]" placeholders)

Use formal clinical letter style: date, recipient address block, "Dear Colleague" salutation, \
signed body paragraphs, and "Yours sincerely" close.
Write only the letter. No meta-commentary, disclaimers, or markdown headers.\
""",

    "discharge_summary": """\
You are an experienced hospital clinician drafting a discharge summary for the GP and patient record.
Write a comprehensive discharge summary based on the patient documentation provided.

Use the following section headings:
PATIENT DETAILS
ADMISSION DETAILS (date, admitting team, admitting diagnosis)
DISCHARGE DIAGNOSIS
REASON FOR ADMISSION
RELEVANT BACKGROUND (PMH, regular medications, allergies, social history)
CLINICAL COURSE (chronological account of treatment, procedures, response)
INVESTIGATIONS (key results — labs, imaging, histology, microbiology)
MEDICATIONS ON DISCHARGE (name / dose / frequency / duration)
CONDITION ON DISCHARGE
FOLLOW-UP PLAN (outpatient appointments, pending results, GP actions)
OUTSTANDING RESULTS

Write each section concisely. Use plain prose, not bullet points, for the Clinical Course.
Write only the discharge summary. No meta-commentary or disclaimers.\
""",

    "case_writeup": """\
You are an experienced clinician writing a structured case write-up suitable for a case \
conference, grand rounds presentation, or submission to a clinical journal.
Write a formal case write-up based on the patient documentation provided.

Structure the write-up with these headings:
TITLE
ABSTRACT (3-5 sentences: background, case summary, key learning point)
INTRODUCTION (1-2 sentences on clinical relevance or epidemiology)
CASE PRESENTATION
  History of presenting complaint
  Past medical / surgical history
  Medications and allergies
  Social and family history
  Examination findings
  Investigations
  Management
DISCUSSION (differential diagnosis considered, key clinical decisions, unusual features, \
evidence-based rationale for management)
CONCLUSION (1-2 sentences on the learning point)
PATIENT CONSENT: Written informed consent was obtained from the patient.

Write in formal academic clinical English. Use clear prose within each section.
Write only the case write-up. No meta-commentary or disclaimers.\
""",
}


class DocumentDrafter:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def draft(self, notebook_id: str, text: str, document_type: str) -> dict:
        if document_type not in DOCUMENT_TYPES:
            raise ValueError(f"Unknown document type: {document_type!r}")

        system_prompt = _SYSTEM_PROMPTS[document_type]
        type_label    = DOCUMENT_TYPES[document_type]

        user_prompt = (
            f"=== PATIENT DOCUMENTATION ===\n{text}\n\n"
            f"Draft the {type_label} now. "
            "Write only the document itself, fully formatted and ready to use."
        )

        logger.info(
            "DocumentDrafter: generating '%s' for notebook %s", document_type, notebook_id
        )

        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                options={"temperature": 0.3},
            )
            content = resp["message"]["content"].strip()
        except Exception as e:
            logger.error("DocumentDrafter LLM call failed: %s", e)
            content = f"[Draft generation failed: {e}]"

        return {
            "document_type":       document_type,
            "document_type_label": type_label,
            "content":             content,
            "generated_at":        datetime.now(timezone.utc).isoformat(),
        }

    def draft_all(self, notebook_id: str, text: str, on_progress=None) -> dict:
        """Generate all three document types in parallel and return as a map."""
        def _progress(step: str, pct: int):
            if on_progress:
                on_progress(step, pct)

        _progress("Starting document generation…", 10)
        results: dict = {}
        labels = list(DOCUMENT_TYPES.keys())
        total = len(labels)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futures = {
                ex.submit(self.draft, notebook_id, text, doc_type): doc_type
                for doc_type in labels
            }
            for i, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                doc_type = futures[future]
                results[doc_type] = future.result()
                label = DOCUMENT_TYPES[doc_type]
                pct = int(10 + (i / total) * 85)
                _progress(f"Drafted {label}…", pct)

        return results
