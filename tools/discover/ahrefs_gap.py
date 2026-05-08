"""ahrefs_gap — Competitor keyword-gap discovery.

For each named competitor, we ask Ahrefs for their top organic keywords and
subtract anything FirstMovers already ranks for. Survivors are competitor
keywords representing genuine content gaps.

Defaults: McKinsey, Accenture, Deloitte, HubSpot — see
`identities.GAP_DISCOVERY_COMPETITORS`. The agent feeds in one
`mcp__ahrefs__site-explorer-organic-keywords` response per competitor.

Filters:
  - Drop keywords already in our inventory's organic_keywords
  - Drop keywords that exact-match any inventory focus_keyword
  - Optional KD ceiling (Ahrefs keyword difficulty 0-100)
  - Volume floor — too low and the gap isn't worth filling

Pure parsing.
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

from ..inventory import Inventory
from . import Audience, Candidate, Intent
from .gsc import _route_audience, _route_category, _route_intent

# Demand floor — Ahrefs estimated monthly volume
AHREFS_MIN_VOLUME: Final[int] = 50

# Difficulty ceiling — beyond this we likely can't outrank a Fortune-50
# competitor in 6 months. 60 is conservative for a small consulting brand.
AHREFS_MAX_KD: Final[int] = 60

# AI-relevance markers. The competitor-gap source is for our space — AI
# automation, AI consulting, agentic systems. A "hubspot" or "tam sam som"
# keyword is a real competitor ranking but isn't FM-relevant. Require at
# least one of these tokens to appear in the keyword.
AI_RELEVANCE_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "ai", "a.i.", "artificial intelligence",
        "gpt", "chatgpt", "claude", "gemini", "llm",
        "agentic", "agent", "agents",
        "automation", "automate",
        "prompt", "prompt engineering",
        "copilot", "machine learning", "ml",
        "rag", "vector",
        "openai", "anthropic",
    }
)


def discover(
    competitor: str,
    raw_response: Any,
    inventory: Inventory,
    *,
    min_volume: int = AHREFS_MIN_VOLUME,
    max_kd: int = AHREFS_MAX_KD,
    top_n: int = 25,
    require_ai_relevance: bool = True,
) -> list[Candidate]:
    """Extract competitor-gap candidates from one Ahrefs organic-keywords response.

    `competitor` is the host (e.g. "mckinsey.com") — used in `discovery_id`
    and `discovery_evidence`. Also used to compute the brand-stem filter
    (e.g. "hubspot" -> drop "hubspot login", "hubspot academy", etc).

    `require_ai_relevance=True` (default) drops keywords without any AI
    marker token (see AI_RELEVANCE_TOKENS). Set False for non-AI niches.
    """
    rows = _extract_rows(raw_response)
    out: list[Candidate] = []
    seen_keywords: set[str] = set()

    inv_focus = inventory.all_focus_keywords()
    inv_organic = inventory.all_organic_keywords()
    inv_known = inv_focus | inv_organic

    competitor_brand_stem = _competitor_brand_stem(competitor)

    for row in rows:
        if not isinstance(row, dict):
            continue
        keyword = (row.get("keyword") or row.get("term") or "").strip()
        if not keyword:
            continue
        kw_lower = keyword.lower()
        if kw_lower in seen_keywords:
            continue
        if kw_lower in inv_known:
            continue

        # Drop the competitor's own brand-name keywords ("hubspot login",
        # "hubspot academy" — we'd never rank for these even if we wrote
        # about them, and they don't match FM's brand).
        if competitor_brand_stem and competitor_brand_stem in kw_lower:
            continue

        # Drop non-AI keywords. The competitor-gap source is for our space
        # specifically; a competitor's "tam sam som" or "como aprender
        # programacion" ranking isn't a gap we should fill.
        if require_ai_relevance and not _has_ai_marker(kw_lower):
            continue

        try:
            volume = int(float(row.get("volume") or row.get("search_volume") or 0))
        except (TypeError, ValueError):
            volume = 0
        try:
            kd = int(float(row.get("difficulty") or row.get("kd") or 0))
        except (TypeError, ValueError):
            kd = 0
        try:
            position = float(row.get("position") or 0)
        except (TypeError, ValueError):
            position = 0.0
        try:
            traffic = int(float(row.get("traffic") or row.get("organic_traffic") or 0))
        except (TypeError, ValueError):
            traffic = 0

        if volume < min_volume:
            continue
        if kd and kd > max_kd:
            continue

        seen_keywords.add(kw_lower)

        out.append(
            Candidate(
                focus_keyword=kw_lower,
                suggested_title_seed=keyword,
                audience=_route_audience(kw_lower),
                category_id=_route_category(kw_lower),
                intent=_route_intent(kw_lower),
                score=_score(volume, kd, traffic),
                rationale=(
                    f"Ahrefs gap from {competitor}: vol {volume}, KD {kd}, "
                    f"competitor pos {position:.0f}, est traffic {traffic}"
                ),
                discovery_source="ahrefs_competitor_gap",
                discovery_id=f"ahrefs:{competitor}:{kw_lower}",
                discovery_evidence={
                    "competitor": competitor,
                    "keyword": keyword,
                    "volume": volume,
                    "difficulty": kd,
                    "competitor_position": position,
                    "competitor_traffic": traffic,
                },
            )
        )

        if len(out) >= top_n:
            break

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
        for key in ("keywords", "rows", "data", "results", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]
    return []


def _score(volume: int, kd: int, traffic: int) -> float:
    """Higher is better. Volume + traffic strong, KD penalizes."""
    vol_term = math.log1p(volume)
    traffic_term = math.log1p(traffic) * 0.5
    kd_penalty = kd / 100.0
    return vol_term + traffic_term - kd_penalty


def _competitor_brand_stem(competitor: str) -> str:
    """Pull the brand stem from a competitor host. "hubspot.com" -> "hubspot".

    Returns lowercased. Empty string for unparseable inputs.
    """
    if not competitor:
        return ""
    host = competitor.strip().lower()
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    # The first label is typically the brand stem (mckinsey.com, hubspot.com)
    parts = host.split(".")
    return parts[0] if parts else ""


def _has_ai_marker(keyword_lower: str) -> bool:
    """True if the keyword contains any AI-relevance token from the allowlist.

    Token-aware: "ai" only matches as a whole word (so "rail" doesn't match).
    """
    import re
    for token in AI_RELEVANCE_TOKENS:
        if " " in token or "." in token:
            # Multi-word tokens — substring match is fine
            if token in keyword_lower:
                return True
        else:
            # Single-word — require word boundary on both sides
            if re.search(rf"\b{re.escape(token)}\b", keyword_lower):
                return True
    return False
