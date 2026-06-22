from __future__ import annotations

import logging
import threading

import chromadb
import torch
from transformers import AutoTokenizer, AutoModel

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 100


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + _CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(text):
            break
        start += _CHUNK_SIZE - _CHUNK_OVERLAP
    return chunks


class NotebookRAG:
    """Per-notebook vector store. Each notebook gets its own ChromaDB collection.
    The model is loaded once as a class-level singleton (thread-safe)."""

    _lock = threading.Lock()
    _tokenizer = None
    _model = None
    _chroma: chromadb.PersistentClient | None = None

    @classmethod
    def _ensure_loaded(cls):
        if cls._model is not None:
            return
        with cls._lock:
            if cls._model is not None:
                return
            logger.info("NotebookRAG: loading MedCPT-Query-Encoder…")
            cls._tokenizer = AutoTokenizer.from_pretrained("ncbi/MedCPT-Query-Encoder")
            cls._model = AutoModel.from_pretrained("ncbi/MedCPT-Query-Encoder").to("cpu")
            cls._model.eval()
            cls._chroma = chromadb.PersistentClient(path="./notebook_rag_db")
            logger.info("NotebookRAG: ready")

    @classmethod
    def _collection(cls, notebook_id: str):
        # ChromaDB collection names: alphanumeric + underscores only
        name = "nb_" + notebook_id.replace("-", "")
        return cls._chroma.get_or_create_collection(
            name, metadata={"hnsw:space": "cosine"}
        )

    @classmethod
    def _embed(cls, text: str) -> list[float]:
        inputs = cls._tokenizer(
            [text],
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        ).to("cpu")
        with torch.no_grad():
            out = cls._model(**inputs)
            emb = out.last_hidden_state[:, 0, :]
        return emb.cpu().numpy().tolist()[0]

    @classmethod
    def index_source(
        cls,
        notebook_id: str,
        source_id: str,
        source_name: str,
        content: str,
    ) -> int:
        """Chunk and embed source content into the notebook's collection."""
        try:
            cls._ensure_loaded()
        except Exception as e:
            logger.warning("NotebookRAG: model load failed, skipping index: %s", e)
            return 0

        col = cls._collection(notebook_id)

        # Remove stale chunks for this source before re-indexing
        try:
            col.delete(where={"source_id": {"$eq": source_id}})
        except Exception:
            pass

        chunks = _chunk_text(content)
        if not chunks:
            return 0

        embeddings = [cls._embed(c) for c in chunks]
        ids = [f"{source_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {"source_id": source_id, "source_name": source_name, "chunk_index": i}
            for i in range(len(chunks))
        ]

        col.add(documents=chunks, embeddings=embeddings, ids=ids, metadatas=metadatas)
        logger.info(
            "NotebookRAG: indexed %d chunks from '%s' (notebook %s)",
            len(chunks), source_name, notebook_id,
        )
        return len(chunks)

    @classmethod
    def retrieve(
        cls,
        notebook_id: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """Return the top-k most relevant chunks from this notebook's sources."""
        try:
            cls._ensure_loaded()
        except Exception as e:
            logger.warning("NotebookRAG: model load failed, skipping retrieve: %s", e)
            return []

        col = cls._collection(notebook_id)
        count = col.count()
        if count == 0:
            return []

        results = col.query(
            query_embeddings=[cls._embed(query)],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )

        return [
            {
                "content": doc,
                "source": meta.get("source_name", ""),
                "relevance": round(1 - dist, 3),
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ]

    @classmethod
    def delete_source(cls, notebook_id: str, source_id: str):
        """Remove all indexed chunks belonging to a source."""
        try:
            cls._ensure_loaded()
            col = cls._collection(notebook_id)
            col.delete(where={"source_id": {"$eq": source_id}})
            logger.info("NotebookRAG: deleted chunks for source %s", source_id)
        except Exception as e:
            logger.warning("NotebookRAG: delete_source failed: %s", e)

    @classmethod
    def delete_notebook(cls, notebook_id: str):
        """Drop the entire vector collection for a notebook."""
        try:
            cls._ensure_loaded()
            name = "nb_" + notebook_id.replace("-", "")
            cls._chroma.delete_collection(name)
            logger.info("NotebookRAG: dropped collection for notebook %s", notebook_id)
        except Exception as e:
            logger.warning("NotebookRAG: delete_notebook failed: %s", e)
