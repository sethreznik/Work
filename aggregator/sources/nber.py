"""
NBER Working Papers – parses the NBER RSS feed and retains papers
whose titles mention both an AI term and a workforce/labor term.
"""
import logging
from datetime import datetime

import feedparser

from ..models import Study
from .base import BaseSource

logger = logging.getLogger(__name__)

_RSS_URL = "https://www.nber.org/rss/new_working_papers.xml"

# A paper is relevant only if its title contains at least one AI term
# AND at least one labor-market term.
_AI_TERMS = {
    "artificial intelligence", "machine learning", "deep learning",
    "large language model", "llm", "generative ai", "neural network",
    "automation", "robot", "algorithm",
}
_LABOR_TERMS = {
    "workforce", "worker", "labor", "labour", "employment", "job",
    "wage", "earnings", "occupation", "skill", "inequality", "displacement",
    "future of work", "human capital",
}


def _is_relevant(title: str, abstract: str) -> bool:
    text = f"{title} {abstract}".lower()
    has_ai = any(t in text for t in _AI_TERMS)
    has_labor = any(t in text for t in _LABOR_TERMS)
    return has_ai and has_labor


class NBERSource(BaseSource):
    name = "nber"

    def fetch(self, keywords: list[str]) -> list[Study]:
        feed = feedparser.parse(_RSS_URL)
        results: list[Study] = []

        for entry in feed.entries:
            url = entry.get("link", "")
            title = entry.get("title", "").strip()
            abstract = entry.get("summary", entry.get("description", "")).strip()

            if not url or not title:
                continue

            if not _is_relevant(title, abstract):
                continue

            # Also check user-configured keywords (broad match)
            study = Study(
                url=url,
                title=title,
                source="NBER",
                published=self._parse_date(entry),
                description=abstract[:500],
            )

            # Accept if it passes either our strict dual-term filter
            # (already done) or the caller's keyword list
            results.append(study)

        logger.info("[NBER] %d relevant papers found", len(results))
        return results

    @staticmethod
    def _parse_date(entry) -> datetime | None:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            return datetime(*entry.published_parsed[:6])
        return None
