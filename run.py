#!/usr/bin/env python3
"""
AI Studies Aggregator – entry point.

Usage:
    python run.py                  Run once and exit (good for cron)
    python run.py --daemon         Run daily at the time set in config.yaml
    python run.py --dry-run        Fetch and print matches without sending email
    python run.py --test-email     Send a test email to verify SMTP settings
    python run.py --config PATH    Use an alternate config file (default: config.yaml)
"""
import argparse
import logging
import sys
from pathlib import Path

import schedule
import time
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("aggregator")


def load_config(path: str) -> dict:
    cfg_path = Path(path)
    if not cfg_path.exists():
        sys.exit(
            f"Config file not found: {cfg_path}\n"
            "Copy config.yaml.example to config.yaml and fill in your settings."
        )
    with cfg_path.open() as f:
        return yaml.safe_load(f)


def send_test_email(cfg: dict) -> None:
    from datetime import datetime
    from aggregator.models import Study
    from aggregator.notifier import EmailNotifier

    dummy = Study(
        url="https://hai.stanford.edu/research/ai-index",
        title="AI Index Report 2026 — Stanford HAI",
        source="Stanford HAI",
        published=datetime.now(),
        description=(
            "The AI Index tracks, collates, distils, and visualises data related to "
            "artificial intelligence. Its mission is to provide unbiased, rigorously "
            "vetted data for policymakers, researchers, executives, journalists, and "
            "the general public."
        ),
    )
    notifier = EmailNotifier(cfg["email"])
    notifier.send([dummy])
    print("Test email sent successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Studies Aggregator")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--daemon", action="store_true", help="Run on a daily schedule")
    parser.add_argument("--dry-run", action="store_true",
                        help="Fetch and log matches but do not send email or persist state")
    parser.add_argument("--test-email", action="store_true",
                        help="Send a test email to verify SMTP settings")
    args = parser.parse_args()

    cfg = load_config(args.config)

    if args.test_email:
        send_test_email(cfg)
        return

    from aggregator.runner import run_once

    if args.daemon:
        run_at = cfg.get("schedule", {}).get("run_at", "08:00")
        logger.info("Daemon mode: will run daily at %s", run_at)

        # Run immediately on startup, then on schedule
        run_once(cfg, dry_run=args.dry_run)

        schedule.every().day.at(run_at).do(run_once, cfg=cfg, dry_run=args.dry_run)
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        found = run_once(cfg, dry_run=args.dry_run)
        if found:
            print(f"Done — {found} new studies sent to {cfg['email']['to']}")
        else:
            print("Done — no new studies found.")


if __name__ == "__main__":
    main()
