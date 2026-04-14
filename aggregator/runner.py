"""
Core orchestration: fetch from all enabled sources, filter new items,
enrich with AI analysis, send an email digest, then mark everything as seen.
"""
import logging
from datetime import datetime
from typing import Any

from .analyzer import enrich_studies
from .fetcher import fetch_full_text
from .models import Study
from .notifier import EmailNotifier
from .sources.arxiv_source import ArXivSource
from .sources.brookings import BrookingsSource
from .sources.mckinsey import McKinseySource
from .sources.nber import NBERSource
from .sources.stanford_hai import StanfordHAISource
from .storage import SeenStorage

logger = logging.getLogger(__name__)

_SOURCE_CLASSES = {
    "stanford_hai": StanfordHAISource,
    "brookings": BrookingsSource,
    "mckinsey": McKinseySource,
    "nber": NBERSource,
    "arxiv": ArXivSource,
}


def run_once(cfg: dict[str, Any], dry_run: bool = False) -> int:
    """
    One full aggregation cycle.

    Returns the number of new studies found.
    """
    storage = SeenStorage(cfg.get("database", "seen.db"))
    notifier = EmailNotifier(cfg["email"])
    sources_cfg: dict = cfg.get("sources", {})

    all_new: list[Study] = []

    for source_key, cls in _SOURCE_CLASSES.items():
        src_cfg = sources_cfg.get(source_key, {})
        if not src_cfg.get("enabled", True):
            logger.info("Source %s is disabled, skipping.", source_key)
            continue

        keywords: list[str] = src_cfg.get("keywords", [])
        source = cls(src_cfg)

        logger.info("Fetching from %s …", source_key)
        studies = source.safe_fetch(keywords)

        new_studies = [s for s in studies if storage.is_new(s)]
        logger.info("%s → %d total, %d new", source_key, len(studies), len(new_studies))
        all_new.extend(new_studies)

    if not all_new:
        logger.info("No new studies found this run.")
        storage.close()
        return 0

    logger.info("Found %d new studies total.", len(all_new))

    # Sort newest-first (studies without a date go last)
    all_new.sort(key=lambda s: s.published or datetime.min, reverse=True)

    # ── Enrich: fetch full text then run Claude analysis ──────────────────
    max_chars = cfg.get("analysis", {}).get("max_content_chars", 6000)
    logger.info("Fetching full text for %d studies …", len(all_new))
    for study in all_new:
        study.full_text = fetch_full_text(study.url, max_chars=max_chars)

    logger.info("Running Claude analysis …")
    enrich_studies(all_new, cfg)
    # ──────────────────────────────────────────────────────────────────────

    if dry_run:
        logger.info("[dry-run] Would send email for:")
        for s in all_new:
            logger.info("  • [%s] %s", s.source, s.title)
            if s.summary:
                logger.info("    Summary: %s", s.summary[:120])
            for insight in s.insights:
                logger.info("    → %s", insight[:100])
    else:
        notifier.send(all_new)
        for s in all_new:
            storage.mark_seen(s)

    storage.close()
    return len(all_new)
