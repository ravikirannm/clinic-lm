import io
import os
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx
import pytesseract
from liteparse import LiteParse
from PIL import Image

# Explicit tessdata path so the dir is passed as --tessdata-dir to the tesseract
# subprocess regardless of whether TESSDATA_PREFIX is inherited.
_TESSDATA_DIR = os.environ.get("TESSDATA_PREFIX", "/usr/share/tesseract-ocr/4.00/tessdata")
_TESS_CONFIG = f"--tessdata-dir {_TESSDATA_DIR}"

doc_parser = LiteParse(
    ocr_enabled=True,
    ocr_language="eng",
    max_pages=1000,
    dpi=150,
    output_format="markdown",
    image_mode="placeholder",
    extract_links=True,
    preserve_very_small_text=True,
    password=None,
    quiet=False,
    num_workers=4,
)

_MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB

_ALLOWED_EXTENSIONS: set[str] = {
    ".pdf",
    ".docx",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
}

_IMAGE_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp",
}

# Magic-byte signatures → category
_MAGIC: list[tuple[bytes, str]] = [
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "docx"),           # ZIP-based; extension check distinguishes DOCX
    (b"\xff\xd8\xff", "image"),        # JPEG
    (b"\x89PNG\r\n\x1a\n", "image"),  # PNG
    (b"GIF87a", "image"),
    (b"GIF89a", "image"),
    (b"BM", "image"),                  # BMP
    (b"II*\x00", "image"),             # TIFF little-endian
    (b"MM\x00*", "image"),             # TIFF big-endian
]


def _detect_type(data: bytes) -> str | None:
    for sig, kind in _MAGIC:
        if data[: len(sig)] == sig:
            return kind
    # WebP: RIFF????WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image"
    return None


def validate_upload(filename: str, file_bytes: bytes) -> tuple[str, str]:
    """
    Validate a file upload for security.

    Returns (safe_filename, detected_type) where detected_type is
    'pdf', 'docx', or 'image'.  Raises ValueError on rejection.
    """
    # Strip directory components and null bytes from filename
    safe_name = Path(filename).name.replace("\x00", "").strip()
    if not safe_name:
        raise ValueError("Invalid filename")

    ext = Path(safe_name).suffix.lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"'{ext}' files are not allowed. Upload PDF, DOCX, or an image.")

    if len(file_bytes) == 0:
        raise ValueError("File is empty")

    if len(file_bytes) > _MAX_FILE_BYTES:
        raise ValueError(f"File exceeds the 20 MB size limit")

    detected = _detect_type(file_bytes)
    if detected is None:
        raise ValueError("File content could not be identified — upload may be corrupt")

    # For ZIP-based formats the magic is the same; use extension to confirm DOCX
    if detected == "docx" and ext != ".docx":
        raise ValueError("File content does not match the declared extension")

    # Ensure images have an image extension
    if detected == "image" and ext not in _IMAGE_EXTENSIONS:
        raise ValueError("File content does not match the declared extension")

    # PDF bytes must carry a .pdf extension
    if detected == "pdf" and ext != ".pdf":
        raise ValueError("File content does not match the declared extension")

    return safe_name, detected


def _clean(text: str) -> str:
    return re.sub(r"\n+", "\n", re.sub(r" +", " ", text)).strip()


def extract_pdf(file_bytes: bytes) -> str:
    return _clean(doc_parser.parse(file_bytes).text)


def extract_docx(file_bytes: bytes) -> str:
    return _clean(doc_parser.parse(file_bytes).text)


def extract_image(file_bytes: bytes) -> str:
    image = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(image, lang="eng", config=_TESS_CONFIG)
    return _clean(text)


def extract_file(file_bytes: bytes, file_type: str) -> str:
    if file_type == "pdf":
        return extract_pdf(file_bytes)
    if file_type == "docx":
        return extract_docx(file_bytes)
    if file_type == "image":
        return extract_image(file_bytes)
    raise ValueError(f"Unsupported file type: {file_type}")


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
