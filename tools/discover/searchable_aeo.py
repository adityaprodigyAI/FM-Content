"""searchable_aeo — AI-engine visibility discovery.

Two extractors:

  - `discover_prompts` — surfaces prompts where competitors get cited by
    ChatGPT / Perplexity / Claude and we DON'T (mention_rate=0%).
  - `discover_topics`  — surfaces topics where our citation rate is below
    a threshold across competitor responses.

Pure parsing of `mcp__claude_ai_searchable__get_visibility_by_prompt` and
`mcp__claude_ai_searchable__get_visibility_by_topic` responses.
"""

from __future__ import annotations

import json
from typing import Any, Final

from ..inventory import Inventory
from . import Audience, Candidate
from .gsc import _route_audience, _route_category, _route_intent

# Filters
SEARCHABLE_MAX_MENTION_RATE: Final[float] = 0.0   # 0% — we're not mentioned at all
SEARCHABLE_MIN_CITATION_COUNT: Final[int] = 5     # at least 5 competitor citations
TOPIC_MAX_COVERAGE: Final[float] = 5.0            # topics where our share is < 5%


def discover_prompts(
    raw_response: Any,
    inventory: Inventory,
) -> list[Candidate]:
    """Surface AI prompts we should be cited for but aren't."""
    rows = _extract_rows(raw_response)
    out: list[Candidate] = []
    seen: set[str] = set()
    inv_focus = inventory.all_focus_keywords()

    for row in rows:
        if not isinstance(row, dict):
            continue
        prompt = str(row.get("prompt") or row.get("query") or "").strip()
        if not prompt:
            continue
        prompt_lower = prompt.lower()
        if prompt_lower in seen:
            continue
        if prompt_lower in inv_focus:
            continue

        try:
            mention_rate = float(row.get("mention_rate", 0))
        except (TypeError, ValueError):
            mention_rate = 0.0
        try:
            citation_count = int(float(row.get("citation_count", 0)))
        except (TypeError, ValueError):
            citation_count = 0

        if mention_rate > SEARCHABLE_MAX_MENTION_RATE:
            continue
        if citation_count < SEARCHABLE_MIN_CITATION_COUNT:
            continue

        seen.add(prompt_lower)
        topic = str(row.get("topic") or "").strip()

        out.append(
            Candidate(
                focus_keyword=prompt_lower,
                suggested_title_seed=prompt,
                audience=_route_audience(prompt_lower),
                category_id=_route_category(prompt_lower + " " + topic.lower()),
                intent=_route_intent(prompt_lower),
                score=_score_prompt(citation_count, mention_rate),
                rationale=(
                    f"Searchable AEO: 0% mention, {citation_count} competitor citations"
                ),
                discovery_source="searchable_prompt",
                discovery_id=f"searchable_prompt:{prompt_lower}",
                discovery_evidence={
                    "prompt": prompt,
                    "topic": topic,
                    "mention_rate": mention_rate,
                    "citation_count": citation_count,
                },
            )
        )

    return out


def discover_topics(
    raw_response: Any,
    inventory: Inventory,
    *,
    max_coverage: float = TOPIC_MAX_COVERAGE,
) -> list[Candidate]:
    """Surface topics where our AI-engine coverage is below threshold."""
    rows = _extract_rows(raw_response)
    out: list[Candidate] = []
    seen: set[str] = set()
    inv_focus = inventory.all_focus_keywords()

    for row in rows:
        if not isinstance(row, dict):
            continue
        topic = str(row.get("topic") or row.get("name") or "").strip()
        if not topic:
            continue
        topic_lower = topic.lower()
        if topic_lower in seen:
            continue
        if topic_lower in inv_focus:
            continue

        try:
            coverage = float(row.get("coverage", row.get("mention_rate", 0)))
        except (TypeError, ValueError):
            coverage = 0.0

        if coverage > max_coverage:
            continue

        seen.add(topic_lower)

        out.append(
            Candidate(
                focus_keyword=topic_lower,
                suggested_title_seed=topic,
                audience=_route_audience(topic_lower),
                category_id=_route_category(topic_lower),
                intent=_route_intent(topic_lower),
                score=max(0.0, 5.0 - coverage),
                rationale=f"Searchable topic at {coverage:.1f}% — competitors dominate",
                discovery_source="searchable_competitor_topic",
                discovery_id=f"searchable_topic:{topic_lower}",
                discovery_evidence={"topic": topic, "coverage": coverage},
            )
        )

    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _extract_rows(raw: Any) -> list[Any]:
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("type") == "text":
        try:
            inner = json.loads(raw[0].get("text", "null"))
            return _extract_rows(inner)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("prompts", "topics", "data", "results", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]
    return []


def _score_prompt(citation_count: int, mention_rate: float) -> float:
    # More competitor citations = more proven demand
    import math
    return math.log1p(citation_count) + max(0.0, 1.0 - mention_rate)
