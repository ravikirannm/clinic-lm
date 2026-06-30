import logging

from transformers import pipeline

from config import TORCH_DEVICE

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 512  # characters per NER pass
_BATCH_SIZE = 8    # chunks processed per GPU call


class ExtractKeywords:
    def __init__(self):
        # pipeline expects an int device index for CUDA or -1 for CPU
        device = 0 if TORCH_DEVICE == "cuda" else -1
        self.clinical_ner = pipeline(
            "ner",
            model="d4data/biomedical-ner-all",
            aggregation_strategy="simple",
            device=device,
        )
        logger.info("ExtractKeywords: NER model loaded on device=%s", TORCH_DEVICE)

    def get_clinical_ner_results(self, clinical_text: str) -> list[str]:
        # Build all chunks first, then run a single batched pipeline call
        chunks = [
            clinical_text[start : start + _CHUNK_SIZE]
            for start in range(0, len(clinical_text), _CHUNK_SIZE)
        ]
        if not chunks:
            return []

        batch_results = self.clinical_ner(chunks, batch_size=_BATCH_SIZE)

        entities: set[str] = set()
        # batch_results is a list of lists when input is a list
        for chunk_entities in batch_results:
            for entity in chunk_entities:
                word = entity["word"].strip()
                score = entity["score"]
                if score > 0.7 and not word.startswith("##") and len(word) > 2:
                    entities.add(word.lower())

        keyword_list = sorted(entities)
        logger.info("Extracted %d clinical entities across %d chunks", len(keyword_list), len(chunks))
        return keyword_list
