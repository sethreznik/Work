import logging
from abc import ABC, abstractmethod

import requests

from ..models import Study

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
_TIMEOUT = 25


class BaseSource(ABC):
    name: str

    def __init__(self, cfg: dict | None = None):
        self.cfg = cfg or {}

    def _get(self, url: str, **kwargs) -> requests.Response:
        resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp

    @abstractmethod
    def fetch(self, keywords: list[str]) -> list[Study]:
        """Return recent studies matching at least one keyword."""
        ...

    def safe_fetch(self, keywords: list[str]) -> list[Study]:
        """Wrap fetch() so a single broken source never crashes the run."""
        try:
            return self.fetch(keywords)
        except Exception as exc:
            logger.warning("[%s] fetch failed: %s", self.name, exc)
            return []
