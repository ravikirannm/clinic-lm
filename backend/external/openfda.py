import logging

import requests

logger = logging.getLogger(__name__)


class OpenFDA:
    def __init__(self):
        self.base_url = "https://api.fda.gov/drug/label.json"

    def map_severity(self, description: str) -> str:
        description_lower = description.lower()
        if any(w in description_lower for w in ["fatal", "severe", "contraindicated", "avoid"]):
            return "HIGH"
        elif any(w in description_lower for w in ["monitor", "caution", "decrease"]):
            return "MODERATE"
        return "LOW"

    def fetch_rxnorm_interactions(self, rxcui: str, _drug2_rxcui: str, drug2_name: str) -> dict:
        result = {
            "found": False,
            "severity": "NONE",
            "description": None,
            "source": "openFDA",
            "source_url": f"https://api.fda.gov/drug/label.json?search=openfda.rxcui.exact:{rxcui}"
        }
        try:
            resp = requests.get(
                "https://api.fda.gov/drug/label.json",
                params={"search": f'openfda.rxcui:"{rxcui}"', "limit": 1},
                timeout=8
            )
            logger.info(f"openFDA response for RxCUI {rxcui}: {resp.status_code}")
            if resp.status_code != 200:
                return result
            data = resp.json()
            results = data.get("results", [])
            if not results:
                return result
            interaction_sections = results[0].get("drug_interactions", [])
            if not interaction_sections:
                return result
            interaction_text = " ".join(interaction_sections)
            if drug2_name.lower() in interaction_text.lower():
                result["found"] = True
                result["description"] = interaction_text[:1000] + "..." if len(interaction_text) > 1000 else interaction_text
                result["severity"] = self.map_severity(interaction_text)
        except Exception as e:
            logger.warning(f"openFDA interaction fetch failed: {e}")
        return result

    def fetch_label(self, drug_name: str) -> dict:
        result = {
            "warnings": None,
            "boxed_warning": None,
            "drug_interactions_text": None,
            "source_url": f'https://api.fda.gov/drug/label.json?search=openfda.generic_name:"{drug_name}"&limit=1'
        }
        try:
            resp = requests.get(
                "https://api.fda.gov/drug/label.json",
                params={"search": f'openfda.generic_name:"{drug_name}"', "limit": 1},
                timeout=8
            )
            data = resp.json()
            results = data.get("results", [])
            if not results:
                resp = requests.get(
                    "https://api.fda.gov/drug/label.json",
                    params={"search": f'openfda.brand_name:"{drug_name}"', "limit": 1},
                    timeout=8
                )
                data = resp.json()
                results = data.get("results", [])
            if results:
                label = results[0]
                result["warnings"] = " ".join(label.get("warnings", []))[:1000] or None
                result["boxed_warning"] = " ".join(label.get("boxed_warning", []))[:500] or None
                result["drug_interactions_text"] = " ".join(label.get("drug_interactions", []))[:1500] or None
        except Exception as e:
            logger.warning(f"OpenFDA label fetch failed for {drug_name}: {e}")
        return result

    def fetch_adverse_events(self, drug1: str, drug2: str) -> int | None:
        try:
            query = f'patient.drug.medicinalproduct:"{drug1}"+AND+patient.drug.medicinalproduct:"{drug2}"'
            resp = requests.get(
                "https://api.fda.gov/drug/event.json",
                params={"search": query, "count": "serious"},
                timeout=8
            )
            data = resp.json()
            results = data.get("results", [])
            if results:
                return sum(r.get("count", 0) for r in results)
            return 0
        except Exception as e:
            logger.warning(f"OpenFDA adverse event count failed: {e}")
            return None
