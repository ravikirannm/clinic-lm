import logging

import ollama
from pydantic import BaseModel

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 10000
_CHUNK_OVERLAP = 400


class _TitleAndSummary(BaseModel):
    title: str
    summary: str


class _Documentation(BaseModel):
    documentation: str


def generate_notebook_content(sources: list[dict]) -> dict:
    combined = "\n\n---\n\n".join(
        f"Source: {s['name']}\n{s['content']}"
        for s in sources
    )

    client = ollama.Client(host=OLLAMA_BASE_URL)

    chunks = _chunk_text(combined)
    logger.warning(f"Chunks: {len(chunks)}")
    chunk_docs: list[str] = []
    for i, chunk in enumerate(chunks):
        try:
            logger.warning(f"Chunk Size: {len(chunk)}")
            doc = _generate_chunk_documentation(client, chunk)
            if doc:
                chunk_docs.append(doc)
        except Exception as e:
            logger.error("chunk %d documentation failed: %s", i, e, exc_info=True)

    if not chunk_docs:
        names = ", ".join(s["name"] for s in sources)
        return {
            "title": "Untitled notebook",
            "summary": f"Sources added: {names}. Connect Ollama to generate AI documentation.",
            "documentation": "",
        }

    try:
        documentation = _combine_documentation(client, chunk_docs)
    except Exception as e:
        logger.error("combine documentation failed: %s", e, exc_info=True)
        documentation = "\n\n".join(chunk_docs)

    try:
        ts = _generate_title_and_summary(client, documentation)
    except Exception as e:
        logger.error("title/summary generation failed: %s", e, exc_info=True)
        names = ", ".join(s["name"] for s in sources)
        ts = {
            "title": "Untitled notebook",
            "summary": f"Sources added: {names}. Connect Ollama to generate AI documentation.",
        }

    return {
        "title": ts["title"],
        "summary": ts["summary"],
        "documentation": documentation,
    }


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + _CHUNK_SIZE
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


def _generate_chunk_documentation(client: ollama.Client, chunk: str) -> str:
    prompt = (
        "You are a medical-scientific documentation assistant. "
        "Given the following clinical text excerpt, produce a JSON object with one key:\n"
        '  "documentation" – concise medical-scientific documentation of the key clinical points '
        "including pathophysiology, diagnostic criteria, treatment, and evidence.\n\n"
        f"Text:\n{chunk}"
    )
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=_Documentation.model_json_schema(),
    )
    return _Documentation.model_validate_json(response["message"]["content"]).documentation


def _combine_documentation(client: ollama.Client, chunk_docs: list[str]) -> str:
    if len(chunk_docs) == 1:
        return chunk_docs[0]

    sections = "\n\n---\n\n".join(
        f"Section {i + 1}:\n{doc}" for i, doc in enumerate(chunk_docs)
    )
    prompt = (
        "You are a medical-scientific documentation assistant. "
        "Given the following documentation sections extracted from clinical sources, "
        "produce a JSON object with one key:\n"
        '  "documentation" – a single comprehensive, well-structured medical-scientific document '
        "that integrates all sections, removes redundancy, and organizes content by topic "
        "(pathophysiology, diagnostic criteria, treatment protocols, drug classes, evidence levels, "
        "clinical relevance). Be thorough and accurate.\n\n"
        f"Sections:\n{sections}"
    )
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=_Documentation.model_json_schema(),
    )
    return _Documentation.model_validate_json(response["message"]["content"]).documentation


def _generate_title_and_summary(client: ollama.Client, documentation: str) -> dict:
    prompt = (
        "You are a medical-scientific summarization engine. "
        "Read the clinical documentation below and extract a title and summary, using ONLY information "
        "explicitly present in the documentation. Do not add outside medical knowledge.\n\n"
        "Output rules:\n"
        "- Return ONLY a single valid JSON object. No markdown fences, no preamble, no trailing text.\n"
        "- Keys must be exactly: title, summary\n"
        '  "title": concise notebook title capturing the main topic, ≤10 words, plain words only, '
        "no brackets or special characters\n"
        '  "summary": 4-6 sentences, plain language, covering the most clinically important points only\n\n'
        f"Documentation:\n{documentation[:4000]}"
    )
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=_TitleAndSummary.model_json_schema(),
    )
    return _TitleAndSummary.model_validate_json(response["message"]["content"]).model_dump()
