import logging

import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.orphadata.com"
_HEADERS = {"Accept": "application/json"}


class OrphaDataClient:
    def search_by_hpo(self, hpo_id: str) -> dict:
        """
        Find rare diseases associated with an HPO term.
        Returns {"diseases": [...], "total": int} where each disease is
        {"orpha_code": str, "name": str}.
        """        
        try:
            resp = requests.get(
                f"{_BASE}/rd-phenotypes/hpoids/{hpo_id}",
                headers=_HEADERS,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()            
            diseases = self._parse_diseases(data)
            total = data.get("total_results") or data.get("total") or len(diseases)
            return {"diseases": diseases, "total": total}
        except Exception as e:
            logger.warning("Orphadata HPO search failed for '%s': %s", hpo_id, e)
            return {"diseases": [], "total": 0}

    # ── Flexible parser handles multiple Orphadata response formats ────────────

    def _parse_diseases(self, data: dict) -> list[dict]:
        # Format A: {"data": [...]} list at top level
        raw = data.get("data", [])
        if isinstance(raw, dict):
            # Format B: {"data": {"results": [...]}}
            raw = raw.get("results", [])

        diseases = []
        for item in (raw if isinstance(raw, list) else []):
            # Get the nested Disorder dictionary if it exists, otherwise fall back to item
            disorder = item.get("Disorder") if isinstance(item.get("Disorder"), dict) else item
            
            orpha = (
                disorder.get("ORPHAcode")
                or disorder.get("orpha_code")
                or disorder.get("OrphaCode")
            )
            name = (
                disorder.get("Preferred term")
                or disorder.get("preferred_term")
                or disorder.get("name")
                or ""
            )
            if orpha:
                diseases.append({
                    "orpha_code": f"ORPHA:{orpha}",
                    "name": name,
                })
        return diseases
