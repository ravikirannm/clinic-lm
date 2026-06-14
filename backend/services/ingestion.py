import io
from html.parser import HTMLParser

import httpx
import pdfplumber


def extract_pdf(file_bytes: bytes) -> str:
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    return "\n".join(pages).strip()


def extract_url(url: str) -> str:
    response = httpx.get(url, follow_redirects=True, timeout=30)
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "pdf" in content_type:
        return extract_pdf(response.content)

    return _strip_html(response.text)


def _strip_html(html: str) -> str:
    class _Extractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self._skip = False

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "head", "nav", "footer"):
                self._skip = True

        def handle_endtag(self, tag):
            if tag in ("script", "style", "head", "nav", "footer"):
                self._skip = False

        def handle_data(self, data):
            if not self._skip:
                stripped = data.strip()
                if stripped:
                    self.parts.append(stripped)

    p = _Extractor()
    p.feed(html)
    return " ".join(p.parts)
