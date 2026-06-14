import logging

from transformers import pipeline

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 512  # characters per NER pass


class ExtractKeywords:
    def __init__(self):
        self.clinical_ner = pipeline(
            "ner",
            model="d4data/biomedical-ner-all",
            aggregation_strategy="simple",
            device=0,
        )

    def get_clinical_ner_results(self, clinical_text: str) -> list[str]:
        entities: set[str] = set()

        # Slide over the full text in overlapping chunks so no content is skipped
        for start in range(0, len(clinical_text), _CHUNK_SIZE):
            chunk = clinical_text[start : start + _CHUNK_SIZE]
            results = self.clinical_ner(chunk)
            for entity in results:
                word = entity["word"].strip()
                score = entity["score"]
                if score > 0.7 and not word.startswith("##") and len(word) > 2:
                    entities.add(word.lower())

        keyword_list = sorted(entities)
        logger.info("Extracted %d clinical entities across %d chunks", len(keyword_list), -(-len(clinical_text) // _CHUNK_SIZE))
        return keyword_list
