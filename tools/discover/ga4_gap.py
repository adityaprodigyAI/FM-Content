"""ga4_gap — High-traffic-page-without-cluster discovery.

Surfaces pages with rising sessions over the last 28 days that lack
supporting cluster content. For each rising page, propose a companion blog
post that would feed the rising page traffic and create a topical cluster.

The companion post's slug is intentionally DIFFERENT from the rising page's
slug — we're proposing a NEW post, not replacing the existing one. The
cannibalization gate then validates the proposed slug + focus keyword
against the full inventory.

Pure parsing.
"""

from __future__ import annotations

import json
import math
from typing import Any, Final

from ..inventory import Inventory
from . import Audience, Candidate
from .gsc import _route_audience, _route_category, _route_intent

# Floors
GA4_MIN_SESSIONS: Final[int] = 100        # over 28d
GA4_MIN_GROWTH_RATIO: Final[float] = 1.10  # +10% vs prior 28d


def discover(
    raw_response: Any,
    inventory: Inventory,
    *,
    min_sessions: int = GA4_MIN_SESSIONS,
    min_growth_ratio: float = GA4_MIN_GROWTH_RATIO,
) -> list[Candidate]:
    """Extract candidates from a GA4 run_report response with sessions delta.

    Expected report shape: dimensions=["pagePath"], metrics=["sessions"]
    with comparisons or a separate prior-period response merged in. The
    parser tolerates either.

    For each rising page, generates a companion-post candidate with:
      - focus_keyword = "<rising page topic> companion guide"
      - slug          = "<rising_slug>-explained"  (different from the
                        rising page's slug — guaranteed)
    """
    rows = _extract_rows(raw_response)
    out: list[Candidate] = []
    seen_paths: set[str] = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("pagePath") or row.get("page_path") or row.get("page") or "").strip()
        if not path or path in seen_paths:
            continue

        try:
            sessions = int(float(row.get("sessions", 0)))
        except (TypeError, ValueError):
            sessions = 0
        try:
            prior_sessions = int(float(row.get("prior_sessions", row.get("sessions_prior", 0))))
        except (TypeError, ValueError):
            prior_sessions = 0

        growth_ratio = (sessions / prior_sessions) if prior_sessions > 0 else float("inf")

        if sessions < min_sessions:
            continue
        if prior_sessions > 0 and growth_ratio < min_growth_ratio:
            continue

        # Skip if the proposed companion slug already exists in inventory
        rising_slug = _slug_from_path(path)
        if not rising_slug:
            continue
        proposed_slug = f"{rising_slug}-explained"
        if proposed_slug in inventory.all_slugs():
            continue

        # Title seed: turn "/ai-workflow-automation/" into "AI workflow automation, explained"
        title_seed = rising_slug.replace("-", " ")
        focus_keyword = f"{title_seed} explained"

        # Skip if focus keyword would exact-match an inventory focus keyword
        if focus_keyword.lower() in inventory.all_focus_keywords():
            continue

        seen_paths.add(path)

        out.append(
            Candidate(
                focus_keyword=focus_keyword.lower(),
                suggested_title_seed=f"{title_seed.title()}, Explained",
                audience=_route_audience(focus_keyword.lower()),
                category_id=_route_category(focus_keyword.lower()),
                intent=_route_intent(focus_keyword.lower()),
                score=_score(sessions, growth_ratio),
                rationale=(
                    f"GA4: page {path} grew {sessions} sessions/28d "
                    f"(growth {growth_ratio:.2f}x) — needs supporting cluster post"
                ),
                discovery_source="ga4_high_traffic_gap",
                discovery_id=f"ga4:{rising_slug}",
                discovery_evidence={
                    "page_path": path,
                    "sessions": sessions,
                    "prior_sessions": prior_sessions,
                    "growth_ratio": growth_ratio if math.isfinite(growth_ratio) else None,
                },
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
        for key in ("rows", "data", "results", "items", "report"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
    return []


def _slug_from_path(path: str) -> str:
    """Pull the slug out of a GA4 pagePath like '/ai-workflow-automation/'."""
    if not path:
        return ""
    p = path.strip().lower()
    if p.startswith("http"):
        # Strip protocol + host
        try:
            after = p.split("://", 1)[1]
            p = "/" + after.split("/", 1)[1] if "/" in after else "/"
        except IndexError:
            pass
    p = p.strip("/").split("/")[-1] if p.strip("/") else ""
    return p


def _score(sessions: int, growth_ratio: float) -> float:
    growth = min(growth_ratio, 5.0) if math.isfinite(growth_ratio) else 2.0
    return math.log1p(sessions) * 0.5 + growth
