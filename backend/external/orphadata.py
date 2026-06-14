import logging

import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.orphadata.com"
_HEADERS = {"Accept": "application/json"}


class OrphaDataClient:
    def search_by_hpo(self, hpo_id: str, page: int = 1) -> dict:
        """
        Find rare diseases associated with an HPO term.
        Returns {"diseases": [...], "total": int} where each disease is
        {"orpha_code": str, "name": str}.
        """
        try:
            resp = requests.get(
                f"{_BASE}/rd-phenotypes/hpo/{hpo_id}/{page}",
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
        for item in raw if isinstance(raw, list) else []:
            orpha = (
                item.get("ORPHAcode")
                or item.get("orpha_code")
                or item.get("OrphaCode")
            )
            name = (
                item.get("Preferred term")
                or item.get("preferred_term")
                or item.get("name")
                or ""
            )
            if orpha:
                diseases.append({
                    "orpha_code": f"ORPHA:{orpha}",
                    "name": name,
                })
        return diseases
