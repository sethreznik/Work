import sqlite3
from datetime import datetime
from .models import Study


class SeenStorage:
    """SQLite-backed store that tracks which study URLs have already been reported."""

    def __init__(self, db_path: str = "seen.db"):
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_studies (
                url      TEXT PRIMARY KEY,
                title    TEXT NOT NULL,
                source   TEXT NOT NULL,
                seen_at  TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def is_new(self, study: Study) -> bool:
        row = self.conn.execute(
            "SELECT url FROM seen_studies WHERE url = ?", (study.url,)
        ).fetchone()
        return row is None

    def mark_seen(self, study: Study) -> None:
        self.conn.execute(
            """INSERT OR IGNORE INTO seen_studies (url, title, source, seen_at)
               VALUES (?, ?, ?, ?)""",
            (study.url, study.title, study.source, datetime.utcnow().isoformat()),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
