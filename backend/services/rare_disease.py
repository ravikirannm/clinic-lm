import concurrent.futures
import logging
from collections import defaultdict

import ollama

from config import OLLAMA_BASE_URL, OLLAMA_MODEL
from services.data_model import SymptomList
from services.notebook_rag import NotebookRAG
from external.nlm_clinical import NLMClinicalClient
from external.orphadata import OrphaDataClient

logger = logging.getLogger(__name__)

_nlm = NLMClinicalClient()
_orpha = OrphaDataClient()

_SYSTEM = (
    "You are a clinical phenotype extraction specialist. "
    "Extract distinct, specific clinical symptom and sign terms from the given medical text. "
    "Use precise medical terminology (e.g. 'ataxia', 'hepatosplenomegaly', 'sensorineural hearing loss'). "
    "Avoid broad categories. Output 5–12 terms as a JSON list."
)


class RareDiseaseService:
    def __init__(self):
        self.client = ollama.Client(host=OLLAMA_BASE_URL)

    def analyze(self, notebook_id: str, text: str) -> dict:
        # ── Step 1: notebook RAG for additional context ───────────────────────
        notebook_chunks: list = []
        if notebook_id:
            try:
                notebook_chunks = NotebookRAG.retrieve(notebook_id, text[:500], top_k=4)
            except Exception as e:
                logger.warning("NotebookRAG retrieval failed: %s", e)

        context_block = "\n".join(c["content"] for c in notebook_chunks) if notebook_chunks else ""

        # ── Step 2: LLM extracts specific symptom terms ───────────────────────
        user_prompt = (
            f"=== CLINICAL NOTE ===\n{text}\n\n"
            + (f"=== ADDITIONAL SOURCE CONTEXT ===\n{context_block}\n\n" if context_block else "")
            + "Extract the specific clinical symptom and sign terms as a JSON list."
        )
        try:
            resp = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": user_prompt},
                ],
                format=SymptomList.model_json_schema(),
                options={"temperature": 0.1},
            )
            symptoms = SymptomList.model_validate_json(resp["message"]["content"]).symptoms
        except Exception as e:
            logger.error("LLM symptom extraction failed: %s", e)
            symptoms = []

        logger.info("Rare disease: extracted %d symptoms: %s", len(symptoms), symptoms)

        if not symptoms:
            return {"symptoms_mapped": [], "diseases": []}

        # ── Step 3: NLM HPO lookup for each symptom (parallel) ───────────────
        def lookup_hpo(symptom: str) -> tuple[str, list[dict]]:
            return symptom, _nlm.text_to_hpo(symptom, max_results=2)

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            hpo_lookups = list(ex.map(lambda s: lookup_hpo(s), symptoms))

        # Build mapping: symptom → top HPO hit
        symptoms_mapped: list[dict] = []
        hpo_to_symptom: dict[str, str] = {}

        for symptom, hits in hpo_lookups:
            if hits:
                top = hits[0]
                hpo_id = top["hpo_id"]
                hpo_name = top["name"]
                symptoms_mapped.append({
                    "symptom": symptom,
                    "hpo_id": hpo_id,
                    "hpo_name": hpo_name,
                })
                hpo_to_symptom[hpo_id] = symptom
                logger.debug("HPO mapped: '%s' → %s (%s)", symptom, hpo_id, hpo_name)
            else:
                symptoms_mapped.append({"symptom": symptom, "hpo_id": None, "hpo_name": None})
                logger.debug("HPO: no match for '%s'", symptom)

        mapped_hpos = [m for m in symptoms_mapped if m["hpo_id"]]
        if not mapped_hpos:
            return {"symptoms_mapped": symptoms_mapped, "diseases": []}

        # ── Step 4: Orphadata search per HPO ID (parallel) ───────────────────
        def orpha_search(entry: dict) -> tuple[dict, dict]:
            result = _orpha.search_by_hpo(entry["hpo_id"])
            return entry, result

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            orpha_results = list(ex.map(lambda e: orpha_search(e), mapped_hpos))

        # ── Step 5: Triangulate — rank diseases by how many HPO terms they match
        disease_map: dict[str, dict] = defaultdict(lambda: {
            "orpha_code": "", "name": "", "matched_symptoms": [], "matched_hpos": set()
        })
        hpo_totals: dict[str, int] = {}

        for entry, orpha_result in orpha_results:
            hpo_id = entry["hpo_id"]
            hpo_totals[hpo_id] = orpha_result["total"]

            for disease in orpha_result["diseases"]:
                code = disease["orpha_code"]
                rec = disease_map[code]
                rec["orpha_code"] = code
                rec["name"] = disease["name"] or rec["name"]
                if hpo_id not in rec["matched_hpos"]:
                    rec["matched_hpos"].add(hpo_id)
                    rec["matched_symptoms"].append({
                        "symptom": hpo_to_symptom.get(hpo_id, hpo_id),
                        "hpo_id": hpo_id,
                        "hpo_name": entry["hpo_name"],
                    })

        total_hpos = len(mapped_hpos)
        diseases = sorted(
            [
                {
                    "orpha_code": rec["orpha_code"],
                    "name": rec["name"],
                    "matched_hpo_count": len(rec["matched_hpos"]),
                    "total_queried": total_hpos,
                    "match_score": round(len(rec["matched_hpos"]) / total_hpos, 3),
                    "matched_symptoms": rec["matched_symptoms"],
                }
                for rec in disease_map.values()
                if rec["name"]
            ],
            key=lambda d: d["matched_hpo_count"],
            reverse=True,
        )[:25]

        logger.info(
            "Rare disease: %d HPOs queried, %d unique diseases found, top match: %s",
            total_hpos,
            len(disease_map),
            diseases[0]["name"] if diseases else "none",
        )

        return {
            "symptoms_mapped": symptoms_mapped,
            "hpo_totals": hpo_totals,
            "diseases": diseases,
        }
