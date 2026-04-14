"""
Content fetcher — retrieves readable text from a study URL.

Supports:
  • HTML pages  — strips boilerplate and extracts article body
  • PDF files   — downloads and extracts text from the first ~10 pages

Falls back to the study's existing description on any error.
"""
import io
import logging
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_HTML_TIMEOUT = 20
_PDF_TIMEOUT = 40
_PDF_MAX_BYTES = 3 * 1024 * 1024  # 3 MB — enough for most report intros
_PDF_MAX_PAGES = 12
_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside",
               "form", "button", "noscript", "iframe"]


def fetch_full_text(url: str, max_chars: int = 6000) -> str:
    """
    Return up to *max_chars* of readable text from *url*.
    Returns an empty string on failure.
    """
    try:
        # A quick HEAD request tells us the content type without downloading.
        head = requests.head(url, headers=_HEADERS, timeout=10, allow_redirects=True)
        content_type = head.headers.get("content-type", "").lower()
    except Exception:
        content_type = ""

    is_pdf = "pdf" in content_type or url.lower().split("?")[0].endswith(".pdf")

    try:
        if is_pdf:
            text = _fetch_pdf(url)
        else:
            text = _fetch_html(url)
    except Exception as exc:
        logger.warning("[fetcher] %s — %s", url, exc)
        text = ""

    return text[:max_chars]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _fetch_html(url: str) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=_HTML_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    # Remove noisy boilerplate
    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    # Prefer semantic containers for the article body
    body = (
        soup.find("main")
        or soup.find("article")
        or soup.find(id=re.compile(r"content|main|body|article", re.I))
        or soup.find(class_=re.compile(r"content|main|body|article|post", re.I))
        or soup.body
    )

    raw = (body or soup).get_text(separator=" ", strip=True)
    # Collapse repeated whitespace
    return re.sub(r"\s{2,}", " ", raw).strip()


def _fetch_pdf(url: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("[fetcher] pypdf not installed — skipping PDF extraction")
        return ""

    resp = requests.get(url, headers=_HEADERS, timeout=_PDF_TIMEOUT, stream=True)
    resp.raise_for_status()

    chunks = []
    total = 0
    for chunk in resp.iter_content(chunk_size=65_536):
        chunks.append(chunk)
        total += len(chunk)
        if total >= _PDF_MAX_BYTES:
            break

    pdf_bytes = b"".join(chunks)
    reader = PdfReader(io.BytesIO(pdf_bytes))

    pages_text = []
    for page in reader.pages[:_PDF_MAX_PAGES]:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            continue

    raw = "\n".join(pages_text)
    return re.sub(r"\s{2,}", " ", raw).strip()
