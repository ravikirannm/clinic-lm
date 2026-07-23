import logging
import threading

import chromadb
import torch
from transformers import AutoTokenizer, AutoModel, pipeline

logger = logging.getLogger(__name__)

MEDCPT_DB_PATH = "./medcpt_db"


class MedicalRAGRetriever:
    # ─── Article Encoder (indexing-side, class-level singleton) ───
    _article_lock = threading.Lock()
    _article_tokenizer = None
    _article_model = None
    _article_device: str = "cpu"

    def __init__(self, db_path=MEDCPT_DB_PATH):
        import logging
        from config import TORCH_DEVICE
        self._logger = logging.getLogger(__name__)
        # ─── Query Encoder (different from Article Encoder) ───
        self._device = TORCH_DEVICE
        self.query_tokenizer = AutoTokenizer.from_pretrained(
            "ncbi/MedCPT-Query-Encoder"
        )
        self.query_model = AutoModel.from_pretrained(
            "ncbi/MedCPT-Query-Encoder"
        ).to(self._device)
        self.query_model.eval()
        self._logger.info("MedicalRAGRetriever: using device=%s", self._device)
        # ─── Load existing ChromaDB ───────────────────────────
        self.chroma = chromadb.PersistentClient(path=db_path)
        self.collection = self.chroma.get_or_create_collection(
            "medical_docs", metadata={"hnsw:space": "cosine"}
        )

    @classmethod
    def _ensure_article_encoder(cls):
        """Load the Article Encoder (indexing side of MedCPT), once, lazily."""
        if cls._article_model is not None:
            return
        with cls._article_lock:
            if cls._article_model is not None:
                return
            from config import TORCH_DEVICE
            logger.info("MedicalRAGRetriever: loading MedCPT-Article-Encoder…")
            cls._article_device = TORCH_DEVICE
            cls._article_tokenizer = AutoTokenizer.from_pretrained(
                "ncbi/MedCPT-Article-Encoder"
            )
            cls._article_model = AutoModel.from_pretrained(
                "ncbi/MedCPT-Article-Encoder"
            ).to(cls._article_device)
            cls._article_model.eval()
            logger.info("MedicalRAGRetriever: Article-Encoder using device=%s", cls._article_device)

    @classmethod
    def embed_article(cls, text: str) -> list[float]:
        """Embed a document/chunk for indexing, using the Article Encoder."""
        cls._ensure_article_encoder()
        inputs = cls._article_tokenizer(
            [text],
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=512,
        ).to(cls._article_device)

        with torch.no_grad(), torch.amp.autocast(
            cls._article_device, enabled=cls._article_device == "cuda"
        ):
            outputs = cls._article_model(**inputs)
            embedding = outputs.last_hidden_state[:, 0, :]

        return embedding.cpu().float().numpy().tolist()[0]



    # ─── STEP 2: Embed enriched query with MedCPT ─────────
    def embed_query(self, query_text: str):
        inputs = self.query_tokenizer(
            [query_text],
            padding=True,
            truncation=True,
            return_tensors="pt",
            max_length=256,
        ).to(self._device)

        with torch.no_grad(), torch.amp.autocast(self._device, enabled=self._device == "cuda"):
            outputs = self.query_model(**inputs)
            embedding = outputs.last_hidden_state[:, 0, :]

        return embedding.cpu().float().numpy().tolist()[0]

    # ─── STEP 3: Retrieve from ChromaDB ───────────────────
    def retrieve(self, variants: list, top_k=8) -> list[str]:
        # Package with source info for Qwen context
        retrieved = []
        for enriched_query in variants:
            if isinstance(enriched_query, (set, list)):
                current_query = ", ".join(list(enriched_query))
            else:
                current_query = str(enriched_query)
            query_vector = self.embed_query(current_query)

            results = self.collection.query(
                query_embeddings=[query_vector],
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )

            docs = results["documents"][0]
            metas = results["metadatas"][0]
            scores = results["distances"][0]

            
            for doc, meta, score in zip(docs, metas, scores):
                retrieved.append({
                    "content": doc,
                    "source": meta.get("source", "unknown"),
                    "relevance": round(1 - score, 3)  # cosine → similarity
                })

        return retrieved