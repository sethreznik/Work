"""
Claude-powered study analyzer.

For each new study the runner discovers, this module:
  1. Assembles a prompt from the study's metadata and fetched full text.
  2. Calls Claude Opus (with adaptive thinking) to produce:
       • A 2-3 sentence executive summary of the findings.
       • 3-5 specific, action-oriented insights for the team to promote internally.
  3. Returns the results as structured data attached to the Study object.

Prompt caching: the system prompt is stable across all studies in a single run,
so we mark it with cache_control to avoid paying for it on every call.
"""
import json
import logging
import os
from typing import Any

import anthropic

from .models import Study

logger = logging.getLogger(__name__)

_MODEL = "claude-opus-4-6"

_SYSTEM = (
    "You are a senior analyst embedded in a research team that tracks the intersection "
    "of artificial intelligence and the future of work. Your job is to help busy "
    "researchers and executives quickly understand new studies.\n\n"
    "When given a study, you produce TWO things:\n\n"
    "1. SUMMARY — A 2-3 sentence executive summary that describes what the study "
    "actually found (not just what it is about). Lead with the headline finding.\n\n"
    "2. INSIGHTS — Exactly 3 to 5 specific, action-oriented insights the team should "
    "consider promoting internally. Each insight should go beyond the abstract — "
    "connect the finding to implications for labor markets, organizational strategy, "
    "policy, or workforce planning. Write them as a professional analyst would brief "
    "a senior stakeholder."
)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 sentence executive summary of the study's key findings."
        },
        "insights": {
            "type": "array",
            "items": {"type": "string"},
            "description": "3-5 specific, actionable insights for the internal team."
        }
    },
    "required": ["summary", "insights"],
    "additionalProperties": False
}


def _make_client(cfg: dict[str, Any]) -> anthropic.Anthropic:
    api_key = cfg.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError(
            "No Claude API key found. Set 'anthropic_api_key' in config.yaml "
            "or the ANTHROPIC_API_KEY environment variable."
        )
    return anthropic.Anthropic(api_key=api_key)


def _build_user_message(study: Study) -> str:
    parts = [
        f"Title: {study.title}",
        f"Source: {study.source}",
        f"URL: {study.url}",
    ]
    if study.published:
        parts.append(f"Published: {study.published.strftime('%Y-%m-%d')}")

    content = study.full_text or study.description
    if content:
        parts.append(f"\nContent:\n{content}")
    else:
        parts.append("\n(No full text available — work from the title and source alone.)")

    return "\n".join(parts)


def enrich_study(study: Study, client: anthropic.Anthropic, model: str = _MODEL) -> None:
    """
    Call Claude to generate a summary and insights, then attach them to *study* in place.
    Logs a warning and leaves summary/insights empty on any API error.
    """
    user_content = _build_user_message(study)

    try:
        # The system prompt is the same for every study in a run.
        # We cache it with cache_control so only the first call pays full price.
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": _SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _OUTPUT_SCHEMA,
                }
            },
        )

        # Extract the JSON text block (thinking blocks are filtered out)
        text = next(
            (b.text for b in response.content if b.type == "text"), ""
        )
        if not text:
            logger.warning("[analyzer] Empty response for '%s'", study.title)
            return

        data = json.loads(text)
        study.summary = data.get("summary", "")
        study.insights = data.get("insights", [])

        cache_read = getattr(response.usage, "cache_read_input_tokens", 0)
        logger.info(
            "[analyzer] '%s' — %d output tokens (cache_read=%d)",
            study.title[:60],
            response.usage.output_tokens,
            cache_read,
        )

    except anthropic.APIError as exc:
        logger.warning("[analyzer] API error for '%s': %s", study.title, exc)
    except Exception as exc:
        logger.warning("[analyzer] Unexpected error for '%s': %s", study.title, exc)


def enrich_studies(
    studies: list[Study],
    cfg: dict[str, Any],
) -> None:
    """
    Enrich a list of studies in place.
    Creates a single Anthropic client shared across all calls in this run
    (so the cached system prompt is reused efficiently).
    """
    analysis_cfg = cfg.get("analysis", {})
    if not analysis_cfg.get("enabled", True):
        logger.info("[analyzer] Analysis disabled in config, skipping.")
        return

    model = analysis_cfg.get("model", _MODEL)

    try:
        client = _make_client(cfg)
    except ValueError as exc:
        logger.warning("[analyzer] %s — skipping analysis.", exc)
        return

    for study in studies:
        enrich_study(study, client, model)
