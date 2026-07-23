import logging
import os
from pathlib import Path

import chromadb

from config import RAG_DOCS_DIR
from services.ingestion import extract_file, validate_upload
from services.notebook_rag import _chunk_text
from services.rag_retriever import MEDCPT_DB_PATH, MedicalRAGRetriever

logger = logging.getLogger(__name__)


def _safe_name(filename: str) -> str:
    name = Path(filename).name.replace("\x00", "").strip()
    if not name:
        raise ValueError("Invalid filename")
    return name


def list_docs() -> list[dict]:
    os.makedirs(RAG_DOCS_DIR, exist_ok=True)
    docs = []
    for filename in sorted(os.listdir(RAG_DOCS_DIR)):
        path = os.path.join(RAG_DOCS_DIR, filename)
        if os.path.isfile(path):
            stat = os.stat(path)
            docs.append({
                "name": filename,
                "size": stat.st_size,
                "modified": int(stat.st_mtime),
            })
    return docs


def save_doc(filename: str, file_bytes: bytes) -> str:
    """Validate and write an uploaded document into RAG_DOCS_DIR. Raises ValueError on rejection."""
    safe_name, _ = validate_upload(filename, file_bytes)
    os.makedirs(RAG_DOCS_DIR, exist_ok=True)
    with open(os.path.join(RAG_DOCS_DIR, safe_name), "wb") as f:
        f.write(file_bytes)
    return safe_name


def delete_doc(filename: str) -> bool:
    safe_name = _safe_name(filename)
    path = os.path.join(RAG_DOCS_DIR, safe_name)
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True


def _get_collection(chroma: chromadb.PersistentClient):
    try:
        chroma.delete_collection("medical_docs")
    except Exception:
        pass
    return chroma.get_or_create_collection("medical_docs", metadata={"hnsw:space": "cosine"})


def rebuild_index() -> dict:
    """Clear medical_docs and re-embed every document currently in RAG_DOCS_DIR."""
    os.makedirs(RAG_DOCS_DIR, exist_ok=True)
    chroma = chromadb.PersistentClient(path=MEDCPT_DB_PATH)
    collection = _get_collection(chroma)

    indexed = 0
    errors: list[dict] = []

    for filename in sorted(os.listdir(RAG_DOCS_DIR)):
        path = os.path.join(RAG_DOCS_DIR, filename)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                file_bytes = f.read()
            _, file_type = validate_upload(filename, file_bytes)
            content = extract_file(file_bytes, file_type)
            chunks = _chunk_text(content)
            if not chunks:
                continue
            embeddings = [MedicalRAGRetriever.embed_article(c) for c in chunks]
            ids = [f"{filename}_{i}" for i in range(len(chunks))]
            metadatas = [
                {"source": filename, "chunk_index": i} for i in range(len(chunks))
            ]
            collection.add(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)
            indexed += 1
        except Exception as exc:
            logger.warning("rag_docs: failed to index '%s': %s", filename, exc)
            errors.append({"file": filename, "error": str(exc)})

    logger.info(
        "rag_docs: rebuilt medical_docs — %d documents indexed, %d chunks, %d errors",
        indexed, collection.count(), len(errors),
    )
    return {"documents_indexed": indexed, "chunks": collection.count(), "errors": errors}


def ensure_indexed() -> None:
    """Startup check: build the medical_docs index if it's empty but source files exist."""
    os.makedirs(RAG_DOCS_DIR, exist_ok=True)
    chroma = chromadb.PersistentClient(path=MEDCPT_DB_PATH)
    collection = chroma.get_or_create_collection("medical_docs", metadata={"hnsw:space": "cosine"})

    if collection.count() > 0:
        logger.info("rag_docs: medical_docs already indexed (%d chunks)", collection.count())
        return

    has_files = any(
        os.path.isfile(os.path.join(RAG_DOCS_DIR, f)) for f in os.listdir(RAG_DOCS_DIR)
    )
    if not has_files:
        logger.info("rag_docs: medical_docs is empty and %s has no files — skipping", RAG_DOCS_DIR)
        return

    logger.info("rag_docs: medical_docs is empty — building index from %s", RAG_DOCS_DIR)
    rebuild_index()
