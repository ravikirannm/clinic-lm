import logging
import re
import time

from ddgs import DDGS

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 2


def search_tool(query: str) -> str:
    query = re.sub(r"(\d+)\+(\d+)", r"\1/\2", query)
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, region='us-en', safesearch='off', max_results=5))
            if results:
                return "\n\n".join(f"Source: {r['title']}\n{r['body']}" for r in results)
            return ""
        except Exception as e:
            logger.warning("Web search attempt %d/%d failed for '%s': %s", attempt, _MAX_RETRIES, query, e)
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_DELAY)
    return ""
