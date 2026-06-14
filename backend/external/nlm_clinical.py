from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

_CLINICAL_TABLES_BASE = "https://clinicaltables.nlm.nih.gov/api"
_MEDLINEPLUS_SEARCH   = "https://wsearch.nlm.nih.gov/ws/query"


def _strip_html(raw: str) -> str:
    """Remove HTML tags and collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


class NLMClinicalClient:

    # ── HPO term lookup ───────────────────────────────────────────────────────

    def text_to_hpo(self, symptom: str, max_results: int = 3) -> list[dict]:
        """
        Map a free-text symptom to HPO term(s) via the NLM Clinical Tables API.
        Returns a list of {"hpo_id": ..., "name": ...} dicts.
        """
        try:
            resp = requests.get(
                f"{_CLINICAL_TABLES_BASE}/hpo/v3/search",
                params={"terms": symptom, "maxList": max_results, "df": "id,name"},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            if data[0] > 0 and data[3]:
                return [{"hpo_id": row[0], "name": row[1]} for row in data[3]]
        except Exception as e:
            logger.warning("NLM HPO lookup failed for '%s': %s", symptom, e)
        return []

    # ── Clinical guideline lookup via MedlinePlus Health Topics ──────────────

    def fetch_guidelines(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Search NLM MedlinePlus Health Topics for clinical guideline content.

        MedlinePlus topics are curated by NLM clinical specialists and synthesise
        recommendations from major guideline bodies (AHA, ADA, NHLBI, USPSTF, CDC,
        NIH, etc.).  Each topic includes a structured summary with management
        recommendations, diagnostic criteria, and treatment targets.

        Returns list of dicts compatible with the guideline consumer in
        ``services/guidelines_conformance.py``:
        [{"id", "title", "abstract", "source", "pub_types", "url"}]
        """
        if not query:
            return []

        try:
            resp = requests.get(
                _MEDLINEPLUS_SEARCH,
                params={"db": "healthTopics", "term": query, "retmax": max_results},
                timeout=10,
            )
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
        except Exception as e:
            logger.warning("NLM MedlinePlus search failed for '%s': %s", query, e)
            return []

        results: list[dict] = []
        for doc in root.findall(".//document"):
            url = doc.get("url", "")

            def _text(name: str) -> str:
                el = doc.find(f"content[@name='{name}']")
                return (el.text or "") if el is not None else ""

            title   = _text("title")
            summary = _strip_html(_text("FullSummary"))
            snippet = _strip_html(_text("snippet"))

            # Prefer FullSummary; fall back to snippet
            abstract = (summary or snippet)[:1200]

            if not title:
                continue

            results.append({
                "id":        url,
                "title":     title,
                "abstract":  abstract,
                "url":       url,
                "source":    "NLM MedlinePlus",
                "pub_types": ["Guideline", "Health Topic"],
            })
            logger.debug("NLM guideline topic: %s — %s", title, url)

        logger.info(
            "NLM MedlinePlus: %d health-topic guideline records for query '%s'",
            len(results), query,
        )
        return results

    # ── NCBI NLM Catalog — guideline publications ─────────────────────────────

    def search_nlm_catalog(self, query: str, max_results: int = 3) -> list[dict]:
        """
        Search the NCBI NLM Catalog (books, journals, guidelines) for official
        clinical guideline publications.

        This supplements MedlinePlus by surfacing formal guideline documents
        (e.g. USPSTF recommendations, IOM reports, CDC manuals) indexed in the
        NLM library collection but not always in PubMed.

        Returns list of {"id", "title", "abstract", "source", "pub_types"}.
        """
        if not query:
            return []

        try:
            # eutils esearch against the NLM catalog
            search_resp = requests.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                params={
                    "db":     "nlmcatalog",
                    "term":   f"({query}) AND clinical practice guideline[Title]",
                    "retmax": max_results,
                    "retmode": "json",
                },
                timeout=10,
            )
            search_resp.raise_for_status()
            ids = search_resp.json().get("esearchresult", {}).get("idlist", [])

            if not ids:
                # Broader fallback
                search_resp = requests.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={
                        "db":     "nlmcatalog",
                        "term":   f"({query}) AND guideline[Title]",
                        "retmax": max_results,
                        "retmode": "json",
                    },
                    timeout=10,
                )
                search_resp.raise_for_status()
                ids = search_resp.json().get("esearchresult", {}).get("idlist", [])

            if not ids:
                return []

            # esummary to get metadata
            summary_resp = requests.get(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
                params={"db": "nlmcatalog", "id": ",".join(ids), "retmode": "json"},
                timeout=10,
            )
            summary_resp.raise_for_status()
            result_map = summary_resp.json().get("result", {})

            records: list[dict] = []
            for uid in ids:
                doc = result_map.get(uid, {})
                title = doc.get("Title") or doc.get("TitleMain", "")
                if not title:
                    continue
                records.append({
                    "id":        uid,
                    "title":     title,
                    "abstract":  doc.get("Summary", ""),
                    "source":    "NLM Catalog",
                    "pub_types": ["Guideline"],
                })
                logger.debug("NLM Catalog guideline: %s (uid=%s)", title, uid)

            logger.info(
                "NLM Catalog: %d guideline records for query '%s'",
                len(records), query,
            )
            return records

        except Exception as e:
            logger.warning("NLM Catalog search failed for '%s': %s", query, e)
            return []
