"""
Stanford HAI – monitors the news page and the AI Index landing page
for new publications relating to AI and the workforce.
"""
import logging
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..models import Study
from .base import BaseSource

logger = logging.getLogger(__name__)

_BASE = "https://hai.stanford.edu"
_URLS = [
    f"{_BASE}/news",
    f"{_BASE}/research/ai-index",
]


def _parse_page(html: str, page_url: str) -> list[Study]:
    soup = BeautifulSoup(html, "lxml")
    studies: list[Study] = []

    # HAI uses <article> cards with an <h2> or <h3> title and an <a> wrapper.
    # We fall back to any heading inside an <a> if the layout changes.
    articles = soup.find_all("article")
    if not articles:
        # Fallback: look for card-like divs with a heading and a link
        articles = soup.select("div.card, div.post, div.news-item, li.post")

    for art in articles:
        # Find the primary link
        a_tag = art.find("a", href=True)
        if not a_tag:
            continue
        url = urljoin(_BASE, a_tag["href"])

        # Title: prefer a heading element, fall back to the link text
        heading = art.find(["h1", "h2", "h3", "h4"])
        title = (heading.get_text(strip=True) if heading else a_tag.get_text(strip=True))
        if not title:
            continue

        # Description: <p> tags or a meta-description-style element
        p_tags = art.find_all("p")
        description = " ".join(p.get_text(strip=True) for p in p_tags[:2])

        # Date: look for <time> or elements with date-like classes
        published = None
        time_tag = art.find("time")
        if time_tag:
            raw = time_tag.get("datetime") or time_tag.get_text(strip=True)
            for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%dT%H:%M:%S"):
                try:
                    published = datetime.strptime(raw[:len(fmt) + 4].strip(), fmt)
                    break
                except ValueError:
                    continue

        studies.append(Study(
            url=url,
            title=title,
            source="Stanford HAI",
            published=published,
            description=description,
        ))

    return studies


class StanfordHAISource(BaseSource):
    name = "stanford_hai"

    def fetch(self, keywords: list[str]) -> list[Study]:
        results: list[Study] = []
        seen_urls: set[str] = set()

        for url in _URLS:
            try:
                resp = self._get(url)
                studies = _parse_page(resp.text, url)
                for s in studies:
                    if s.url not in seen_urls and s.matches_keywords(keywords):
                        seen_urls.add(s.url)
                        results.append(s)
                logger.info("[Stanford HAI] %s → %d candidates from %s",
                            self.name, len(studies), url)
            except Exception as exc:
                logger.warning("[Stanford HAI] failed to fetch %s: %s", url, exc)

        return results
