from __future__ import annotations

import concurrent.futures
import logging
import re

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

_SYSTEM = """\
You are a medical text de-identification engine. Your ONLY job is to replace Personally \
Identifiable Information (PII) and Protected Health Information (PHI) with bracketed \
placeholders. You must NEVER remove, paraphrase, summarise, or alter any part of the text \
except to substitute identifiers with the placeholders below.

REPLACE each of the following with the corresponding placeholder:
  [PATIENT_NAME]    — patient full name, first name, last name, or initials
  [CLINICIAN_NAME]  — doctor, nurse, therapist, or any clinician's name
  [FACILITY_NAME]   — hospital, clinic, pharmacy, GP practice, or laboratory name
  [DATE_OF_BIRTH]   — explicit date of birth (keep stated age, e.g. "67-year-old", unchanged)
  [DATE]            — any specific calendar date (admission, discharge, appointment, test date)
  [ADDRESS]         — street address, city, county, postcode, or ZIP code
  [PHONE]           — telephone or fax number
  [EMAIL]           — email address
  [PATIENT_ID]      — MRN, NHS number, SSN, national ID, hospital number, or any record number
  [INSURANCE_ID]    — insurance policy or payer ID number

PRESERVE exactly as-is — do NOT touch these under any circumstances:
  ✔ All medical diagnoses, conditions, procedures, and clinical terminology
  ✔ Medications, doses, frequencies, and routes of administration
  ✔ Laboratory values, vital signs, imaging findings, ECG results
  ✔ Symptoms, clinical history, review of systems, social habits (tobacco/alcohol/drugs amounts)
  ✔ Ages expressed as age (e.g. "41-year-old", "age 52") — only [DATE_OF_BIRTH] for actual dates
  ✔ Relative time ("3 weeks ago", "since last month", "for 20 years")
  ✔ Clinical assessments, differential diagnoses, management plans, follow-up instructions
  ✔ All headings, section labels, bullet points, and document structure

Return ONLY the de-identified text with placeholders substituted in. \
Do not add any explanation, commentary, or markdown formatting.\
"""


def _split_into_chunks(text: str, max_words: int = 350) -> list[str]:
    """
    Split text on paragraph boundaries, grouping paragraphs into chunks of
    at most max_words words. Preserves document structure better than word-based slicing.
    """
    paragraphs = re.split(r'\n{2,}', text.strip())
    chunks: list[str] = []
    current: list[str] = []
    current_word_count = 0

    for para in paragraphs:
        para_words = len(para.split())
        # If this single paragraph is already over the limit, emit it alone
        if para_words >= max_words:
            if current:
                chunks.append('\n\n'.join(current))
                current, current_word_count = [], 0
            chunks.append(para)
            continue
        # If adding it would overflow, flush current group first
        if current and current_word_count + para_words > max_words:
            chunks.append('\n\n'.join(current))
            current, current_word_count = [para], para_words
        else:
            current.append(para)
            current_word_count += para_words

    if current:
        chunks.append('\n\n'.join(current))

    return chunks if chunks else [text]


def _deidentify_chunk(client: ollama.Client, chunk: str, index: int) -> str:
    """Send a single chunk to the LLM for PII removal. Returns original on failure."""
    try:
        resp = client.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "De-identify the following medical text. "
                        "Replace ONLY PII/PHI with placeholders. "
                        "Preserve every clinical detail exactly.\n\n"
                        f"{chunk}"
                    ),
                },
            ],
            options={"temperature": 0.0},
        )
        result = resp["message"]["content"].strip()
        if not result:
            logger.warning("Anonymizer: empty response for chunk %d — keeping original", index)
            return chunk
        return result
    except Exception as exc:
        logger.warning("Anonymizer: chunk %d failed (%s) — keeping original", index, exc)
        return chunk  # never lose data on failure


def anonymize(text: str) -> str:
    """
    De-identify PII/PHI from medical text by splitting into paragraph-aware
    chunks, processing them in parallel, and reassembling in order.
    Falls back to the original chunk if the LLM call fails.
    """
    if not text or not text.strip():
        return text

    client = ollama.Client(host=OLLAMA_BASE_URL)
    chunks = _split_into_chunks(text, max_words=350)

    logger.info(
        "Anonymizer: %d chars split into %d chunks", len(text), len(chunks)
    )

    if len(chunks) == 1:
        result = _deidentify_chunk(client, chunks[0], 0)
        logger.info(
            "Anonymizer: done — %d chars in, %d chars out", len(text), len(result)
        )
        return result

    # Process chunks in parallel; preserve ordering via enumeration
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, len(chunks))) as ex:
        future_map = {
            ex.submit(_deidentify_chunk, client, chunk, i): i
            for i, chunk in enumerate(chunks)
        }
        ordered: dict[int, str] = {}
        for future in concurrent.futures.as_completed(future_map):
            idx = future_map[future]
            ordered[idx] = future.result()

    result = '\n\n'.join(ordered[i] for i in range(len(chunks)))
    logger.info(
        "Anonymizer: done — %d chars in, %d chars out (%d chunks)",
        len(text), len(result), len(chunks),
    )
    return result
