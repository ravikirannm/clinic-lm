import logging

import ollama
from pydantic import BaseModel

from config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

_SOURCE_CHAR_LIMIT = 4000


class _TitleAndSummary(BaseModel):
    title: str
    summary: str


class _Documentation(BaseModel):
    documentation: str


def generate_notebook_content(sources: list[dict]) -> dict:
    combined = "\n\n---\n\n".join(
        f"Source: {s['name']}\n{s['content'][:_SOURCE_CHAR_LIMIT]}"
        for s in sources
    )

    client = ollama.Client(host=OLLAMA_BASE_URL)

    try:
        ts = _generate_title_and_summary(client, combined)
    except Exception as e:
        logger.error("title/summary generation failed: %s", e, exc_info=True)
        names = ", ".join(s["name"] for s in sources)
        ts = {"title": "Untitled notebook", "summary": f"Sources added: {names}. Connect Ollama to generate AI documentation."}

    try:
        doc = _generate_documentation(client, combined)
    except Exception as e:
        logger.error("documentation generation failed: %s", e, exc_info=True)
        doc = {"documentation": ""}

    return {
        "title": ts["title"],
        "summary": ts["summary"],
        "documentation": doc["documentation"],
    }


def _generate_title_and_summary(client: ollama.Client, combined: str) -> dict:
    prompt = (
        "You are a medical-scientific assistant. "
        "Given the following clinical sources, produce a JSON object with two keys:\n"
        '  "title"   – concise notebook title capturing the main topic (≤10 words)\n'
        '  "summary" – 4-6 sentence plain-language summary of the most important clinical points\n\n'
        f"Sources:\n{combined}"
    )
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=_TitleAndSummary.model_json_schema(),
    )
    content = response["message"]["content"]
    return _TitleAndSummary.model_validate_json(content).model_dump()


def _generate_documentation(client: ollama.Client, combined: str) -> dict:
    prompt = (
        "You are a medical-scientific documentation assistant. "
        "Given the following clinical sources, produce a JSON object with one key:\n"
        '  "documentation" – comprehensive medical-scientific documentation covering '
        "pathophysiology, diagnostic criteria, updated guidelines, treatment protocols, "
        "drug classes, evidence levels, and clinical relevance. Be thorough and structured.\n\n"
        f"Sources:\n{combined}"
    )
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        format=_Documentation.model_json_schema(),
    )
    content = response["message"]["content"]
    return _Documentation.model_validate_json(content).model_dump()
