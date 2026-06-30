import chromadb
import torch
from transformers import AutoTokenizer, AutoModel, pipeline

class MedicalRAGRetriever:
    def __init__(self, db_path="./medcpt_db"):
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
        self.collection = self.chroma.get_or_create_collection("medical_docs")



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