import io
from html.parser import HTMLParser

import httpx
from liteparse import LiteParse
import re

parser = LiteParse(
    ocr_enabled=True,              # Enable OCR (default: True)
    ocr_language="eng",            # Tesseract language code
    max_pages=1000,                # Max pages to parse
    dpi=150,                       # Rendering DPI
    output_format="markdown",          # "json" | "text" | "markdown"
    image_mode="placeholder",      # Markdown image handling: "placeholder" | "off" | "embed"
    extract_links=True,            # Render [text](url) links in markdown output
    preserve_very_small_text=True, # Keep tiny text
    password=None,                 # Password for protected documents
    quiet=False,                   # Suppress progress output
    num_workers=4,                 # Concurrent OCR workers
)

def extract_pdf(file_bytes: bytes) -> str:
    result = parser.parse(file_bytes)
    return re.sub(r'\n+', '\n', re.sub(r' +', ' ', result.text))


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
