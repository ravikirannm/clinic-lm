import concurrent.futures
import logging
import re
import time

import requests

from config import ICD11_CLIENT_ID, ICD11_CLIENT_SECRET

logger = logging.getLogger(__name__)

_NLM_URL = "https://clinicaltables.nlm.nih.gov/api/icd11_codes/v3/search"
_TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
_WHO_BASE = "https://id.who.int/icd/release/11/2024-01/mms"
_WHO_SEARCH = f"{_WHO_BASE}/search"
_STRIP_HTML = re.compile(r"<[^>]+>")
_MAX_CHILDREN = 15
_MAX_ANCESTORS = 6
_TREE_MAX_ANCESTORS = 4
_TREE_MAX_CHILDREN = 10
_TREE_MAX_GRANDCHILDREN = 6


class ICD11Client:
    def __init__(self):
        self._token: str | None = None
        self._token_expires: float = 0.0

    # ── WHO OAuth ─────────────────────────────────────────────────────────────

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            logger.debug("WHO token: cached, expires in %.0fs", self._token_expires - time.time())
            return self._token
        logger.info("WHO token: fetching new token (client_id prefix='%s')", ICD11_CLIENT_ID[:8])
        resp = requests.post(
            _TOKEN_URL,
            data={
                "client_id": ICD11_CLIENT_ID,
                "client_secret": ICD11_CLIENT_SECRET,
                "scope": "icdapi_access",
                "grant_type": "client_credentials",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires = time.time() + data.get("expires_in", 3600)
        logger.info("WHO token: obtained, expires in %ds", data.get("expires_in", 3600))
        return self._token

    def _who_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Accept": "application/json",
            "Accept-Language": "en",
            "API-Version": "v2",
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _browser_url(self) -> str:
        # The WHO ICD-11 SPA doesn't reliably support deep-link hash routing.
        # Return the base browse URL so the user at least gets to the browser
        # and can search for the code manually.
        return "https://icd.who.int/browse/2024-01/mms/en"

    def _entity_id(self, uri: str) -> str:
        # WHO search responses use http:// while _WHO_BASE is https://, so normalize first.
        # Preserve full path after the base so composite IDs like "525744634/unspecified"
        # are kept intact rather than being truncated to just "unspecified".
        prefix = _WHO_BASE + "/"
        normalized = uri.replace("http://", "https://", 1)
        if normalized.startswith(prefix):
            return normalized[len(prefix):].rstrip("/")
        return uri.rstrip("/").split("/")[-1]

    def _title(self, raw) -> str:
        if isinstance(raw, dict):
            raw = raw.get("@value", "")
        return _STRIP_HTML.sub("", raw or "")

    def _fetch_who_entity(self, entity_id: str) -> dict:
        resp = requests.get(
            f"{_WHO_BASE}/{entity_id}",
            headers=self._who_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ── NLM search (no auth) ──────────────────────────────────────────────────

    def fetch_icd11(self, search_terms: list[str]) -> list[dict]:
        seen: set = set()
        all_results: list[dict] = []

        def _search_term(term: str) -> list[dict]:
            try:
                resp = requests.get(
                    _NLM_URL,
                    params={"terms": term, "df": "code,title"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return [{"code": m[0], "title": m[1]} for m in (data[3] or [])]
            except Exception as e:
                logger.warning("NLM ICD-11 search failed for '%s': %s", term, e)
            return []

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(_search_term, t) for t in search_terms]
            for f in futures:
                for item in f.result():
                    if item["code"] not in seen:
                        seen.add(item["code"])
                        all_results.append(item)

        return all_results

    # ── WHO tree (requires credentials) ───────────────────────────────────────

    def code_to_entity_id(self, code: str) -> str | None:
        if not ICD11_CLIENT_ID:
            logger.warning("code_to_entity_id: ICD11_CLIENT_ID not set")
            return None

        def _search(q: str) -> str | None:
            try:
                logger.info("WHO search: q='%s' (looking for code='%s')", q, code)
                resp = requests.get(
                    _WHO_SEARCH,
                    headers=self._who_headers(),
                    params={"q": q, "flatResults": True},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                top_keys = list(data.keys())
                entities = data.get("matches", []) + data.get("destinationEntities", [])
                found_codes = [m.get("theCode") for m in entities]
                logger.info(
                    "WHO search q='%s': HTTP %d, response keys=%s, %d entities, codes=%s",
                    q, resp.status_code, top_keys, len(entities), found_codes[:10],
                )
                for m in entities:
                    if m.get("theCode") == code:
                        eid = self._entity_id(m.get("id", ""))
                        logger.info("WHO search: exact code match '%s' → entity_id=%s", code, eid)
                        return eid
                for m in entities:
                    if m.get("theCode", "").startswith(code):
                        eid = self._entity_id(m.get("id", ""))
                        logger.info(
                            "WHO search: prefix match code='%s' via '%s' → entity_id=%s",
                            code, m.get("theCode"), eid,
                        )
                        return eid
                logger.warning("WHO search q='%s': no match for code='%s' in returned codes=%s", q, code, found_codes)
            except Exception as e:
                logger.error("WHO search failed for q='%s': %s: %s", q, type(e).__name__, e)
            return None

        result = _search(code) or _search(code.split(".")[0])
        if not result:
            logger.warning("code_to_entity_id: exhausted all searches for code='%s'", code)
        return result

    def get_entity(self, entity_id: str) -> dict:
        if not ICD11_CLIENT_ID:
            return {"error": "ICD11_CLIENT_ID not configured"}
        try:
            data = self._fetch_who_entity(entity_id)
        except Exception as e:
            logger.error("WHO entity fetch failed for %s: %s", entity_id, e)
            return {}

        code = data.get("code", "")
        title = self._title(data.get("title"))
        browser_url = self._browser_url()

        # ── Ancestor chain (sequential — each level depends on previous) ──────
        ancestors: list[dict] = []
        current_data = data
        for _ in range(_MAX_ANCESTORS):
            parent_uris = current_data.get("parent", [])
            if not parent_uris:
                break
            pid = self._entity_id(parent_uris[0])
            if not pid or pid == entity_id:
                break
            try:
                pd = self._fetch_who_entity(pid)
                ancestors.insert(0, {
                    "entity_id": pid,
                    "code": pd.get("code", ""),
                    "title": self._title(pd.get("title")),
                })
                current_data = pd
            except Exception:
                break

        # ── Children resolved in parallel ─────────────────────────────────────
        child_uris = data.get("child", [])
        total_children = len(child_uris)
        child_uris = child_uris[:_MAX_CHILDREN]

        def _resolve_child(uri: str) -> dict:
            cid = self._entity_id(uri)
            try:
                cd = self._fetch_who_entity(cid)
                return {
                    "entity_id": cid,
                    "code": cd.get("code", ""),
                    "title": self._title(cd.get("title")),
                    "has_children": bool(cd.get("child")),
                }
            except Exception:
                return {"entity_id": cid, "code": "", "title": "", "has_children": False}

        children: list[dict] = []
        if child_uris:
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
                children = list(ex.map(_resolve_child, child_uris))

        return {
            "entity_id": entity_id,
            "code": code,
            "title": title,
            "ancestors": ancestors,
            "children": children,
            "has_children": total_children > 0,
            "children_truncated": total_children > _MAX_CHILDREN,
            "browser_url": browser_url,
        }

    # ── Pre-built tree (WHO API) ──────────────────────────────────────────────

    def _find_entity_id(self, code: str, title: str) -> str | None:
        logger.info("_find_entity_id: code='%s' title='%s'", code, title)
        eid = self.code_to_entity_id(code)
        if eid:
            logger.info("_find_entity_id: resolved via code lookup → %s", eid)
            return eid
        if not title:
            logger.warning("_find_entity_id: code lookup failed and no title to fall back on")
            return None
        logger.info("_find_entity_id: code lookup failed, trying title search for '%s'", title)
        try:
            # No flatResults — hierarchical search returns richer entity data
            resp = requests.get(
                _WHO_SEARCH,
                headers=self._who_headers(),
                params={"q": title},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            entities = data.get("matches", []) + data.get("destinationEntities", [])
            logger.info(
                "WHO title search '%s': %d entities, raw_ids=%s, stem_ids=%s, codes=%s",
                title,
                len(entities),
                [m.get("id") for m in entities[:3]],
                [m.get("stemId") for m in entities[:3]],
                [m.get("theCode") for m in entities[:5]],
            )
            if entities:
                exact = next((m for m in entities if m.get("theCode") == code), None)
                if exact:
                    raw_id = exact.get("id", "")
                    eid = self._entity_id(raw_id)
                    logger.info(
                        "_find_entity_id: exact code match theCode='%s' → eid='%s'",
                        code, eid,
                    )
                else:
                    # No exact match. First result is often a residual child whose URI is
                    # "{parent_entity_id}/unspecified" or "{parent_entity_id}/other".
                    # Stripping that suffix gives us the parent entity — likely our target.
                    first = entities[0]
                    raw_id = first.get("id", "")
                    eid = self._entity_id(raw_id)
                    if "/" in eid:
                        parent_eid = eid.split("/")[0]
                        logger.info(
                            "_find_entity_id: no exact match for '%s', inferred parent entity '%s' from residual '%s'",
                            code, parent_eid, eid,
                        )
                        eid = parent_eid
                    else:
                        logger.info(
                            "_find_entity_id: no exact match for '%s', using first result theCode='%s' eid='%s'",
                            code, first.get("theCode"), eid,
                        )
                return eid or None
        except Exception as e:
            logger.error("WHO title search failed for '%s': %s: %s", title, type(e).__name__, e)
        logger.warning("_find_entity_id: all lookups failed for code='%s'", code)
        return None

    def build_tree(self, code: str, title: str = "") -> dict | None:
        if not ICD11_CLIENT_ID:
            logger.warning("build_tree: ICD11_CLIENT_ID not configured")
            return None
        logger.info("build_tree: START code='%s' title='%s'", code, title)

        entity_id = self._find_entity_id(code, title)
        if not entity_id:
            logger.warning("build_tree: ABORT — entity_id not found for code='%s'", code)
            return None
        logger.info("build_tree: entity_id=%s for code='%s'", entity_id, code)

        try:
            data = self._fetch_who_entity(entity_id)
        except Exception as e:
            logger.error("build_tree: root entity fetch failed for %s: %s", entity_id, e)
            return None

        # Ancestors (sequential, cap at 4 levels)
        ancestors: list[dict] = []
        current_data = data
        for level in range(_TREE_MAX_ANCESTORS):
            parent_uris = current_data.get("parent", [])
            if not parent_uris:
                logger.debug("build_tree: ancestor chain ends at level %d (no parent)", level)
                break
            pid = self._entity_id(parent_uris[0])
            # Stop if we've reached the linearization root (no valid entity id)
            if not pid or pid == entity_id or pid in ("mms", "entity"):
                logger.debug("build_tree: ancestor walk reached root at level %d (pid='%s')", level, pid)
                break
            try:
                pd = self._fetch_who_entity(pid)
                ancestors.insert(0, {
                    "entity_id": pid,
                    "code": pd.get("code", ""),
                    "title": self._title(pd.get("title")),
                })
                current_data = pd
                logger.debug("build_tree: ancestor[%d] code=%s", level, pd.get("code"))
            except Exception as e:
                logger.warning("build_tree: ancestor fetch failed at level %d: %s", level, e)
                break

        # Level-1 children, each expanded to level-2 grandchildren
        child_uris = data.get("child", [])[:_TREE_MAX_CHILDREN]
        logger.info("build_tree: code='%s' has %d children (capped at %d)", code, len(data.get("child", [])), _TREE_MAX_CHILDREN)

        def resolve_with_grandchildren(uri: str) -> dict:
            cid = self._entity_id(uri)
            try:
                cd = self._fetch_who_entity(cid)
                gc_uris = cd.get("child", [])[:_TREE_MAX_GRANDCHILDREN]

                def resolve_gc(gc_uri: str) -> dict:
                    gcid = self._entity_id(gc_uri)
                    try:
                        gcd = self._fetch_who_entity(gcid)
                        return {
                            "entity_id": gcid,
                            "code": gcd.get("code", ""),
                            "title": self._title(gcd.get("title")),
                            "has_children": bool(gcd.get("child")),
                            "children": [],
                        }
                    except Exception as e:
                        logger.warning("build_tree: grandchild %s fetch failed: %s", gcid, e)
                        return {"entity_id": gcid, "code": "", "title": "", "has_children": False, "children": []}

                grandchildren: list[dict] = []
                if gc_uris:
                    with concurrent.futures.ThreadPoolExecutor(max_workers=_TREE_MAX_GRANDCHILDREN) as ex:
                        grandchildren = list(ex.map(resolve_gc, gc_uris))
                return {
                    "entity_id": cid,
                    "code": cd.get("code", ""),
                    "title": self._title(cd.get("title")),
                    "has_children": bool(cd.get("child")),
                    "children": grandchildren,
                }
            except Exception as e:
                logger.warning("build_tree: child %s fetch failed: %s", cid, e)
                return {"entity_id": cid, "code": "", "title": "", "has_children": False, "children": []}

        children: list[dict] = []
        if child_uris:
            with concurrent.futures.ThreadPoolExecutor(max_workers=_TREE_MAX_CHILDREN) as ex:
                children = list(ex.map(resolve_with_grandchildren, child_uris))

        logger.info("build_tree: DONE code='%s' — %d ancestors, %d children", code, len(ancestors), len(children))
        return {
            "entity_id": entity_id,
            "code": data.get("code", "") or code,
            "title": self._title(data.get("title")) or title,
            "has_children": bool(data.get("child")),
            "ancestors": ancestors,
            "children": children,
            "browser_url": self._browser_url(),
        }
