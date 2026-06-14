import logging

import requests

logger = logging.getLogger(__name__)


class RXNavClient:
    def __init__(self, base_url: str = "https://rxnav.nlm.nih.gov/REST"):
        self.base_url = base_url

    def get_rxcui(self, unique_candidates: list) -> dict:
        matched_candidate = None
        rxcui_found = None
        for candidate in unique_candidates:
            try:
                rxnorm_resp = requests.get(
                    "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                    params={"name": candidate, "search": 1},
                    timeout=5
                )
                rxcui = rxnorm_resp.json().get("idGroup", {}).get("rxnormId", [])
                if rxcui:
                    rxcui_found = rxcui[0]
                    matched_candidate = candidate
                    break
            except Exception as e:
                logger.warning(f"RxNorm lookup failed for '{candidate}': {e}")
        return {"rxcui": rxcui_found, "matched_candidate": matched_candidate}
