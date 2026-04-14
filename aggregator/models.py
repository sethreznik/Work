from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Study:
    url: str
    title: str
    source: str
    published: Optional[datetime] = None
    description: str = ""

    # Populated by the fetcher after initial discovery
    full_text: str = ""

    # Populated by the analyzer (Claude)
    summary: str = ""
    insights: list[str] = field(default_factory=list)

    def matches_keywords(self, keywords: list[str]) -> bool:
        """Return True if any keyword appears in the title or description."""
        text = f"{self.title} {self.description}".lower()
        return any(kw.lower() in text for kw in keywords)
