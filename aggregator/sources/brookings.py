"""
Brookings Institution – parses their RSS feed and filters entries
that cover AI and workforce topics.
"""
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser

from ..models import Study
from .base import BaseSource

logger = logging.getLogger(__name__)

# Brookings provides a general RSS feed; we keyword-filter the results.
_RSS_URLS = [
    "https://www.brookings.edu/feed/",
    "https://www.brookings.edu/feed/?topic=artificial-intelligence",
]


def _parse_date(entry) -> datetime | None:
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return parsedate_to_datetime(raw)
            except Exception:
                pass
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime(*entry.published_parsed[:6])
    return None


class BrookingsSource(BaseSource):
    name = "brookings"

    def fetch(self, keywords: list[str]) -> list[Study]:
        results: list[Study] = []
        seen_urls: set[str] = set()

        for feed_url in _RSS_URLS:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    url = entry.get("link", "")
                    if not url or url in seen_urls:
                        continue

                    title = entry.get("title", "").strip()
                    description = entry.get("summary", entry.get("description", "")).strip()
                    # feedparser may return HTML in summary; strip tags simply
                    description = BeautifulSoupLite(description)
                    published = _parse_date(entry)

                    study = Study(
                        url=url,
                        title=title,
                        source="Brookings",
                        published=published,
                        description=description,
                    )
                    if study.matches_keywords(keywords):
                        seen_urls.add(url)
                        results.append(study)

                logger.info("[Brookings] %d matching entries from %s", len(results), feed_url)
            except Exception as exc:
                logger.warning("[Brookings] failed to parse %s: %s", feed_url, exc)

        return results


def BeautifulSoupLite(html: str) -> str:
    """Strip HTML tags from a string without importing BS4 just for this."""
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
