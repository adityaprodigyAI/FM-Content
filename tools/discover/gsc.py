"""gsc — Striking-distance discovery from Google Search Console.

Pulls queries we already rank position 11-30 for over a 28-day window.
These are queries where we're one push away from page 1 — the highest-
conversion content gap to fill.

**The W20 fix lives here.** Before emitting any candidate, this module
asks the inventory: "is the GSC ranking URL for this query already a known
FirstMovers page or post?" If yes, we DROP the candidate — we don't
propose a topic for a query whose URL is already ours.

The agent feeds in a raw `mcp__gsc__get_search_analytics` response with
dimensions=[query, page]. This module parses + filters + scores.

Pure parsing.
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

from ..identities import (
    WP_CATEGORY_AGI,
    WP_CATEGORY_AI_AUTOMATION,
    WP_CATEGORY_AI_CONSULTING,
    WP_CATEGORY_AI_IN_BUSINESS,
    WP_CATEGORY_AI_MARKETING,
    WP_CATEGORY_AI_SALES,
    WP_CATEGORY_AI_TOOLS,
)
from ..inventory import Inventory
from . import Audience, Candidate, Intent

# Striking-distance window — positions 11-30 (just off page 1)
GSC_MIN_POSITION: Final[float] = 11.0
GSC_MAX_POSITION: Final[float] = 30.0

# Demand floor — fewer than this many impressions over 28d isn't worth the
# write effort
GSC_MIN_IMPRESSIONS: Final[int] = 200

# CTR ceiling — if we're already converting on the query, don't crowd it
GSC_MAX_CTR: Final[float] = 0.01  # 1%


_TOPIC_TO_CATEGORY: Final[tuple[tuple[str, int], ...]] = (
    ("ai consulting", WP_CATEGORY_AI_CONSULTING),
    ("ai implementation", WP_CATEGORY_AI_CONSULTING),
    ("ai workflow", WP_CATEGORY_AI_AUTOMATION),
    ("workflow automation", WP_CATEGORY_AI_AUTOMATION),
    ("ai automation", WP_CATEGORY_AI_AUTOMATION),
    ("ai for sales", WP_CATEGORY_AI_SALES),
    ("agentic ai", WP_CATEGORY_AI_SALES),
    ("ai sales", WP_CATEGORY_AI_SALES),
    ("ai marketing", WP_CATEGORY_AI_MARKETING),
    ("marketing automation", WP_CATEGORY_AI_MARKETING),
    ("ai content", WP_CATEGORY_AI_MARKETING),
    ("ai tool", WP_CATEGORY_AI_TOOLS),
    ("chatgpt", WP_CATEGORY_AI_TOOLS),
    ("claude ai", WP_CATEGORY_AI_TOOLS),
    ("agi", WP_CATEGORY_AGI),
    ("artificial general intelligence", WP_CATEGORY_AGI),
)

DEFAULT_CATEGORY: Final[int] = WP_CATEGORY_AI_IN_BUSINESS


def discover(
    raw_response: Any,
    inventory: Inventory,
    *,
    min_position: float = GSC_MIN_POSITION,
    max_position: float = GSC_MAX_POSITION,
    min_impressions: int = GSC_MIN_IMPRESSIONS,
    max_ctr: float = GSC_MAX_CTR,
) -> list[Candidate]:
    """Extract striking-distance candidates from a GSC search-analytics response.

    Returns Candidates with `discovery_source="gsc_striking_distance"`. Drops
    any row whose ranking URL is already in `inventory` (the W20 fix).
    """
    rows = _extract_rows(raw_response)
    out: list[Candidate] = []
    seen_queries: set[str] = set()

    for row in rows:
        try:
            query = _row_field(row, "query") or ""
            page = _row_field(row, "page") or ""
            position = float(_row_field(row, "position") or 0)
            impressions = int(float(_row_field(row, "impressions") or 0))
            clicks = int(float(_row_field(row, "clicks") or 0))
            ctr = float(_row_field(row, "ctr") or 0)
        except (TypeError, ValueError):
            continue

        query = query.strip().lower()
        if not query:
            continue
        if query in seen_queries:
            continue

        # Striking-distance filters
        if not (min_position <= position <= max_position):
            continue
        if impressions < min_impressions:
            continue
        if ctr > max_ctr:
            continue

        # The W20 fix: drop queries whose ranking URL is already on FirstMovers
        if _is_existing_fm_url(page, inventory):
            continue

        seen_queries.add(query)

        out.append(
            Candidate(
                focus_keyword=query,
                suggested_title_seed=query,
                audience=_route_audience(query),
                category_id=_route_category(query),
                intent=_route_intent(query),
                score=_score(impressions, position, clicks),
                rationale=(
                    f"GSC striking-distance: pos {position:.1f}, "
                    f"{impressions} impressions, {clicks} clicks, CTR {ctr:.3%}"
                ),
                discovery_source="gsc_striking_distance",
                discovery_id=f"gsc:{query}",
                discovery_evidence={
                    "query": query,
                    "page": page,
                    "position": position,
                    "impressions": impressions,
                    "clicks": clicks,
                    "ctr": ctr,
                },
            )
        )

    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_existing_fm_url(url: str, inventory: Inventory) -> bool:
    """True if `url` is a firstmovers.ai URL already in the inventory.

    Defends against the W20 bug — GSC striking-distance queries can rank our
    OWN pages, and we should never propose a new topic for a query whose
    target is already ours.
    """
    if not url:
        return False
    cleaned = url.strip().lower()
    if not (cleaned.startswith("https://firstmovers.ai") or cleaned.startswith("http://firstmovers.ai")):
        return False
    # Strict URL match
    if inventory.has_url(cleaned):
        return True
    # Slug match — the URL points at firstmovers.ai but the inventory may
    # store a slightly different URL form. Pull the slug and compare.
    slug = inventory.slug_from_fm_url(cleaned)
    if slug and slug in inventory.all_slugs():
        return True
    return False


def _extract_rows(raw: Any) -> list[Any]:
    """Tolerate the wrapped MCP shape and a few common variants."""
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("type") == "text":
        try:
            inner = json.loads(raw[0].get("text", "null"))
            return _extract_rows(inner)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("rows", "data", "results", "items", "queries"):
            if isinstance(raw.get(key), list):
                return raw[key]
    return []


def _row_field(row: Any, name: str) -> Any:
    """GSC rows can be {keys: [..], <name>: ..} or {<name>: ..} or
    {keys: [query, page], position: ..., impressions: ..., ctr: ..., clicks: ...}.
    """
    if isinstance(row, dict):
        if name in row:
            return row[name]
        if name == "query" and isinstance(row.get("keys"), list) and row["keys"]:
            return row["keys"][0]
        if name == "page" and isinstance(row.get("keys"), list) and len(row["keys"]) >= 2:
            return row["keys"][1]
    return None


def _route_audience(query: str) -> Audience:
    """Heuristic audience routing.

    Done-for-you signals: "consulting", "agency", "managed", "for me", "service",
    "expert", "implementation", "build for", "consultant".

    DIY signals: "how to", "diy", "guide", "tutorial", "self", "learn",
    "checklist", "template", "tool", "setup", "build my own".
    """
    diy_markers = ("how to", "diy", "tutorial", "self", "learn ", "checklist",
                   "template", "build my", "setup", "set up", "step by step")
    if any(m in query for m in diy_markers):
        return "diy"
    return "done-for-you"


def _route_category(query: str) -> int:
    for fragment, cat in _TOPIC_TO_CATEGORY:
        if fragment in query:
            return cat
    return DEFAULT_CATEGORY


def _route_intent(query: str) -> Intent:
    transactional = ("buy", "pricing", "cost", "hire", "vendor", "consultant",
                     "service", "agency", "for sale")
    commercial = ("vs", "best", "top", "compare", "comparison", "review",
                  "alternatives", "recommendation")
    if any(m in query for m in transactional):
        return "transactional"
    if any(m in query for m in commercial):
        return "commercial"
    if query.startswith(("how", "why", "what", "when", "where")):
        return "informational"
    return "informational"


def _score(impressions: int, position: float, clicks: int) -> float:
    """Higher is better. Combines impression volume, position closeness to
    page 1, and click signal (already-clicking queries that we under-rank
    are doubly valuable).
    """
    impression_term = math.log1p(impressions)            # diminishing returns
    position_term = max(0.0, 31.0 - position) / 20.0     # closer to 11 = better
    click_term = math.log1p(clicks) * 0.5
    return impression_term + position_term + click_term
