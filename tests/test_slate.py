"""Tests for tools/slate.py.

Covers aggregation, cannibalization filtering, ranking, deterministic
build, and JSON persistence.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.discover import Candidate
from tools.inventory import Inventory, PublishedPost
from tools.slate import (
    aggregate,
    build_slate,
    load_slate,
    rank_candidates,
    write_slate,
    _slug_from_focus_keyword,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _well_formed_inv() -> Inventory:
    return Inventory(
        posts=[
            PublishedPost(
                id=1, slug="ai-consulting-cost-2026",
                title="How Much Does AI Consulting Cost in 2026?",
                url="https://firstmovers.ai/ai-consulting-cost-2026/",
                published_at="2026-04-15", kind="blog",
                focus_keyword="ai consulting cost",
                organic_keywords=["ai consultant rates", "ai consulting"],
            ),
            PublishedPost(
                id=2, slug="resource-based-economy",
                title="Resource Based Economy",
                url="https://firstmovers.ai/resource-based-economy/",
                published_at="2025-12-01", kind="page",
                focus_keyword="resource based economy",
                organic_keywords=[],
            ),
        ],
        generated_at=_now(),
    )


def _cand(focus_keyword: str, *, source: str = "gsc_striking_distance",
          score: float = 5.0, audience: str = "done-for-you",
          category_id: int = 27, intent: str = "informational") -> Candidate:
    return Candidate(
        focus_keyword=focus_keyword,
        suggested_title_seed=focus_keyword.title(),
        audience=audience,  # type: ignore[arg-type]
        category_id=category_id,
        intent=intent,  # type: ignore[arg-type]
        score=score,
        rationale="test",
        discovery_source=source,  # type: ignore[arg-type]
        discovery_id=f"{source}:{focus_keyword}",
        discovery_evidence={"keyword": focus_keyword},
    )


# ---------- aggregate ----------


def test_aggregate_dedupes_focus_keywords_case_insensitive():
    a = [_cand("AI Workflow Automation"), _cand("how to scale ai")]
    b = [_cand("ai workflow automation"), _cand("agentic ai for sales")]
    merged = aggregate(a, b)
    fks = [c.focus_keyword for c in merged]
    # First-occurrence wins
    assert "AI Workflow Automation" in fks
    assert "ai workflow automation" not in fks
    assert len(merged) == 3


# ---------- rank_candidates ----------


def test_rank_candidates_applies_source_weights():
    cands = [
        _cand("low score gsc", source="gsc_striking_distance", score=3.0),
        _cand("high score aeo", source="searchable_prompt", score=4.0),
    ]
    ranked = rank_candidates(cands)
    # GSC weight 1.4 * 3.0 = 4.2 vs Searchable weight 1.0 * 4.0 = 4.0 -> GSC wins
    assert ranked[0].focus_keyword == "low score gsc"


# ---------- build_slate ----------


def test_build_slate_drops_critical_cannibalization():
    """The W20-style proposal with slug already in inventory must NOT
    appear in the slate."""
    inv = _well_formed_inv()
    cands = [
        _cand("resource based economy"),  # critical: slug + focus_kw match
        _cand("prompt engineering for support"),  # clear
        _cand("ai inbox triage workflows"),  # clear
    ]
    slate = build_slate(week="2026-W22", candidates=cands, inventory=inv)
    fks = [p.focus_keyword for p in slate.proposals]
    assert "resource based economy" not in fks
    assert "prompt engineering for support" in fks


def test_build_slate_caps_at_target_count():
    inv = _well_formed_inv()
    cands = [_cand(f"unique focus {i}") for i in range(20)]
    slate = build_slate(
        week="2026-W22", candidates=cands, inventory=inv, target_count=5
    )
    assert len(slate.proposals) == 5


def test_build_slate_orders_by_weighted_score():
    inv = _well_formed_inv()
    cands = [
        _cand("low score", score=1.0),
        _cand("high score", score=10.0),
        _cand("medium score", score=5.0),
    ]
    slate = build_slate(week="2026-W22", candidates=cands, inventory=inv)
    assert slate.proposals[0].focus_keyword == "high score"
    assert slate.proposals[-1].focus_keyword == "low score"


def test_build_slate_emits_provenance():
    inv = _well_formed_inv()
    cands = [_cand("agentic sales playbook")]
    slate = build_slate(week="2026-W22", candidates=cands, inventory=inv)
    p = slate.proposals[0]
    assert p.discovery_source == "gsc_striking_distance"
    assert p.discovery_id.startswith("gsc_striking_distance:")
    assert p.discovery_evidence["keyword"] == "agentic sales playbook"


def test_build_slate_summary_counts_by_source():
    inv = _well_formed_inv()
    cands = [
        _cand("a", source="gsc_striking_distance"),
        _cand("b", source="gsc_striking_distance"),
        _cand("c", source="searchable_prompt"),
        _cand("d", source="ahrefs_competitor_gap"),
    ]
    slate = build_slate(week="2026-W22", candidates=cands, inventory=inv)
    by = slate.discovery_summary["by_source"]
    assert by["gsc_striking_distance"] == 2
    assert by["searchable_prompt"] == 1
    assert by["ahrefs_competitor_gap"] == 1


def test_build_slate_uses_injected_titles_when_provided():
    inv = _well_formed_inv()
    cands = [_cand("focus")]
    titles = {"focus": {
        "title": "Custom Title",
        "angle": "Custom angle.",
        "outline": ["bullet 1", "bullet 2", "bullet 3"],
    }}
    slate = build_slate(
        week="2026-W22", candidates=cands, inventory=inv,
        titles_by_focus_kw=titles,
    )
    p = slate.proposals[0]
    assert p.working_title == "Custom Title"
    assert p.one_line_angle == "Custom angle."
    assert p.outline_bullets == ["bullet 1", "bullet 2", "bullet 3"]


# ---------- write / load round-trip ----------


def test_write_load_roundtrip(tmp_path: Path):
    inv = _well_formed_inv()
    cands = [_cand("focus a"), _cand("focus b")]
    slate = build_slate(week="2026-W22", candidates=cands, inventory=inv)
    written = write_slate(slate, dir_=tmp_path)
    assert written.exists()
    loaded = load_slate("2026-W22", dir_=tmp_path)
    assert len(loaded.proposals) == len(slate.proposals)
    assert loaded.week == slate.week
    assert loaded.proposals[0].focus_keyword == slate.proposals[0].focus_keyword


# ---------- slug helper ----------


def test_slug_from_focus_keyword_canonicalizes():
    assert _slug_from_focus_keyword("AI Workflow Automation") == "ai-workflow-automation"
    assert _slug_from_focus_keyword("how to use ChatGPT?!") == "how-to-use-chatgpt"
    assert _slug_from_focus_keyword("multiple   spaces") == "multiple-spaces"
