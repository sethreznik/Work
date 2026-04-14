"""
arXiv – queries the arXiv API for recent papers at the intersection of
AI/ML and labor economics, then filters by user keywords.

Categories searched:
  cs.AI   – Artificial Intelligence
  cs.LG   – Machine Learning
  econ.LB – Labor Economics
  econ.GN – General Economics

The query is intentionally broad; keyword filtering narrows it down.
"""
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

from ..models import Study
from .base import BaseSource

logger = logging.getLogger(__name__)

_API_URL = "https://export.arxiv.org/api/query"

# Titles/abstracts must mention at least one labor-market term to pass.
_LABOR_TERMS = {
    "workforce", "worker", "labor", "labour", "employment", "job",
    "wage", "earnings", "occupation", "skill", "displacement",
    "inequality", "future of work", "human capital", "automation",
}

_NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

# arXiv query: papers in cs.AI/cs.LG that mention labor terms in title,
# OR papers in econ.LB (Labor Economics).
_SEARCH_QUERY = (
    "(cat:cs.AI OR cat:cs.LG OR cat:econ.LB OR cat:econ.GN) AND "
    "(ti:workforce OR ti:\"labor market\" OR ti:\"labour market\" OR "
    "ti:employment OR ti:automation OR ti:\"future of work\" OR "
    "ti:\"wage inequality\" OR ti:\"skill biased\" OR ti:\"job displacement\")"
)


class ArXivSource(BaseSource):
    name = "arxiv"

    def fetch(self, keywords: list[str]) -> list[Study]:
        max_results = int(self.cfg.get("max_results", 30))
        return self._fetch(keywords, max_results)

    def _fetch(self, keywords: list[str], max_results: int) -> list[Study]:
        params = {
            "search_query": _SEARCH_QUERY,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_results,
        }

        resp = self._get(_API_URL, params=params)
        root = ET.fromstring(resp.text)

        results: list[Study] = []
        for entry in root.findall("atom:entry", _NS):
            title_el = entry.find("atom:title", _NS)
            id_el = entry.find("atom:id", _NS)
            summary_el = entry.find("atom:summary", _NS)
            published_el = entry.find("atom:published", _NS)

            if title_el is None or id_el is None:
                continue

            title = " ".join((title_el.text or "").split())
            url = (id_el.text or "").strip()
            abstract = " ".join((summary_el.text or "").split()) if summary_el is not None else ""

            published = None
            if published_el is not None and published_el.text:
                try:
                    published = datetime.fromisoformat(published_el.text.rstrip("Z"))
                except ValueError:
                    pass

            study = Study(
                url=url,
                title=title,
                source="arXiv",
                published=published,
                description=abstract[:500],
            )

            # Pass if it matches user keywords OR has a labor term
            text = f"{title} {abstract}".lower()
            if study.matches_keywords(keywords) or any(t in text for t in _LABOR_TERMS):
                results.append(study)

        logger.info("[arXiv] %d relevant papers found", len(results))
        return results
