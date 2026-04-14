"""
McKinsey Global Institute – scrapes the MGI publications page and the
McKinsey Future of Work topic page for new AI/workforce research.

Note: McKinsey's site is largely server-rendered but some pages may
require JavaScript. This scraper does a best-effort HTML fetch; if the
page returns no parseable articles it logs a warning and returns nothing.
"""
import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Study
from .base import BaseSource

logger = logging.getLogger(__name__)

_BASE = "https://www.mckinsey.com"
_URLS = [
    f"{_BASE}/mgi/our-research",
    f"{_BASE}/featured-insights/future-of-work",
    f"{_BASE}/featured-insights/artificial-intelligence",
]


def _parse_page(html: str, source_url: str) -> list[Study]:
    soup = BeautifulSoup(html, "lxml")
    studies: list[Study] = []

    # McKinsey article cards typically sit in <article> or generic div containers.
    # We cast a wide net by looking for any anchor whose href leads to an article.
    candidates = soup.select(
        "article, "
        "div[class*='card'], "
        "div[class*='article'], "
        "div[class*='result'], "
        "li[class*='article']"
    )

    # Deduplicate by URL
    seen: set[str] = set()

    for block in candidates:
        a_tag = block.find("a", href=True)
        if not a_tag:
            continue
        href = a_tag["href"]
        if href.startswith("/"):
            url = urljoin(_BASE, href)
        elif href.startswith("http"):
            url = href
        else:
            continue

        if url in seen:
            continue
        seen.add(url)

        heading = block.find(["h1", "h2", "h3", "h4"])
        title = heading.get_text(strip=True) if heading else a_tag.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        p_tags = block.find_all("p")
        description = " ".join(p.get_text(strip=True) for p in p_tags[:2])

        published = None
        time_tag = block.find("time")
        if time_tag:
            raw = time_tag.get("datetime") or time_tag.get_text(strip=True)
            for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%b. %d, %Y"):
                try:
                    published = datetime.strptime(raw[:20].strip(), fmt)
                    break
                except ValueError:
                    continue

        studies.append(Study(
            url=url,
            title=title,
            source="McKinsey / MGI",
            published=published,
            description=description,
        ))

    return studies


class McKinseySource(BaseSource):
    name = "mckinsey"

    def fetch(self, keywords: list[str]) -> list[Study]:
        results: list[Study] = []
        seen_urls: set[str] = set()

        for url in _URLS:
            try:
                resp = self._get(url)
                studies = _parse_page(resp.text, url)
                before = len(results)
                for s in studies:
                    if s.url not in seen_urls and s.matches_keywords(keywords):
                        seen_urls.add(s.url)
                        results.append(s)
                logger.info("[McKinsey] %d candidates from %s, %d matched keywords",
                            len(studies), url, len(results) - before)
            except Exception as exc:
                logger.warning("[McKinsey] failed to fetch %s: %s", url, exc)

        return results
