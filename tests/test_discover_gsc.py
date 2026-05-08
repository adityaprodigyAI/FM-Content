"""Tests for tools/discover/gsc.py.

The most important test is `test_drops_queries_whose_url_is_already_ours` —
the W20 fix at the discovery layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

from tools.discover.gsc import discover, _is_existing_fm_url
from tools.inventory import Inventory, PublishedPost


def _inv(slugs: list[str]) -> Inventory:
    posts = [
        PublishedPost(
            id=1000 + i,
            slug=slug,
            title=slug.replace("-", " ").title(),
            url=f"https://firstmovers.ai/{slug}/",
            published_at="2026-04-30",
            kind="page" if "page" in slug else "blog",
            focus_keyword=slug.replace("-", " "),
            organic_keywords=["kw1", "kw2"] if "blog" in slug or "page" not in slug else [],
        )
        for i, slug in enumerate(slugs)
    ]
    return Inventory(posts=posts, generated_at=datetime.now(timezone.utc).isoformat())


# ---------- W20 fix: drop queries whose URL is ours ----------


def test_drops_queries_whose_url_is_already_ours():
    """The exact W20 failure mode: GSC returned a query whose `page` was
    https://firstmovers.ai/resource-based-economy/ (already a FM page),
    and the v5 pipeline emitted it as a candidate anyway.
    """
    inv = _inv(["resource-based-economy"])
    raw = {
        "rows": [
            {
                "keys": ["resource based economy", "https://firstmovers.ai/resource-based-economy/"],
                "position": 19.7,
                "impressions": 256,
                "clicks": 1,
                "ctr": 0.0039,
            }
        ]
    }
    candidates = discover(raw, inv)
    assert candidates == [], (
        f"GSC discovery emitted a candidate for a URL that's already ours: {candidates}"
    )


def test_keeps_queries_whose_url_is_not_ours():
    inv = _inv(["something-else"])
    raw = {
        "rows": [
            {
                "keys": ["competitor blog post", "https://example.com/their-blog/"],
                "position": 15,
                "impressions": 500,
                "clicks": 2,
                "ctr": 0.004,
            }
        ]
    }
    candidates = discover(raw, inv)
    assert len(candidates) == 1
    assert candidates[0].focus_keyword == "competitor blog post"


def test_drops_queries_with_existing_fm_slug_even_at_different_url():
    inv = _inv(["resource-based-economy"])
    raw = {
        "rows": [
            {
                "keys": ["resource based economy", "https://firstmovers.ai/RESOURCE-BASED-ECONOMY/"],
                "position": 12,
                "impressions": 300,
                "clicks": 0,
                "ctr": 0.0,
            }
        ]
    }
    candidates = discover(raw, inv)
    assert candidates == []


def test_is_existing_fm_url_helper():
    inv = _inv(["foo", "bar"])
    assert _is_existing_fm_url("https://firstmovers.ai/foo/", inv) is True
    assert _is_existing_fm_url("https://firstmovers.ai/foo", inv) is True
    assert _is_existing_fm_url("https://firstmovers.ai/baz/", inv) is False
    assert _is_existing_fm_url("https://example.com/foo/", inv) is False
    assert _is_existing_fm_url("", inv) is False


# ---------- Striking-distance filters ----------


def test_drops_queries_above_max_position():
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["far back query", "https://example.com/"],
             "position": 50, "impressions": 500, "clicks": 0, "ctr": 0.0},
        ]
    }
    assert discover(raw, inv) == []


def test_drops_queries_below_min_position():
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["already top 10", "https://example.com/"],
             "position": 5, "impressions": 500, "clicks": 50, "ctr": 0.10},
        ]
    }
    assert discover(raw, inv) == []


def test_drops_low_impression_queries():
    """Below GSC_MIN_IMPRESSIONS (default 25) — drop the row."""
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["low demand", "https://example.com/"],
             "position": 15, "impressions": 5, "clicks": 0, "ctr": 0.0},
        ]
    }
    assert discover(raw, inv) == []


def test_drops_high_ctr_queries():
    """If we're already converting, don't crowd the query with another post."""
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["already converting", "https://example.com/"],
             "position": 15, "impressions": 1000, "clicks": 100, "ctr": 0.10},
        ]
    }
    assert discover(raw, inv) == []


def test_drops_serp_feature_pollution():
    """Long quoted phrases that look like People-Also-Ask snippets, not real queries."""
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ['"content intelligence" a content marketer\'s guide to natural language generation',
                     "https://example.com/"],
             "position": 28, "impressions": 30, "clicks": 0, "ctr": 0.0},
            {"keys": ["this is a very long natural language phrase with way too many words for a real user query",
                     "https://example.com/"],
             "position": 15, "impressions": 100, "clicks": 0, "ctr": 0.0},
        ]
    }
    assert discover(raw, inv) == [], "SERP-feature pollution leaked through"


def test_keeps_short_real_user_queries():
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["agi timeline", "https://example.com/"],
             "position": 14, "impressions": 100, "clicks": 0, "ctr": 0.0},
            {"keys": ["ai consulting cost", "https://example.com/"],
             "position": 18, "impressions": 60, "clicks": 0, "ctr": 0.0},
        ]
    }
    cands = discover(raw, inv)
    assert {c.focus_keyword for c in cands} == {"agi timeline", "ai consulting cost"}


# ---------- Provenance ----------


def test_candidates_have_full_provenance():
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["how to use ai for sales", "https://example.com/"],
             "position": 15, "impressions": 500, "clicks": 1, "ctr": 0.002},
        ]
    }
    candidates = discover(raw, inv)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.discovery_source == "gsc_striking_distance"
    assert c.discovery_id.startswith("gsc:")
    assert c.discovery_evidence["query"] == "how to use ai for sales"
    assert c.discovery_evidence["page"] == "https://example.com/"
    assert c.discovery_evidence["impressions"] == 500
    assert c.discovery_evidence["position"] == 15.0


# ---------- Audience routing ----------


def test_audience_routes_diy_for_how_to_queries():
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["how to set up ai workflows", "https://example.com/"],
             "position": 15, "impressions": 500, "clicks": 1, "ctr": 0.002},
        ]
    }
    candidates = discover(raw, inv)
    assert candidates[0].audience == "diy"


def test_audience_routes_done_for_you_for_consulting_queries():
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["best ai consulting firm", "https://example.com/"],
             "position": 15, "impressions": 500, "clicks": 1, "ctr": 0.002},
        ]
    }
    candidates = discover(raw, inv)
    assert candidates[0].audience == "done-for-you"


# ---------- MCP wrapper handling ----------


def test_handles_mcp_text_wrapper():
    import json
    inv = _inv(["unrelated"])
    raw = [{
        "type": "text",
        "text": json.dumps({"rows": [
            {"keys": ["valid query", "https://example.com/"],
             "position": 15, "impressions": 500, "clicks": 1, "ctr": 0.002}
        ]})
    }]
    candidates = discover(raw, inv)
    assert len(candidates) == 1
    assert candidates[0].focus_keyword == "valid query"


# ---------- Dedupe ----------


def test_dedupes_repeated_queries():
    inv = _inv(["unrelated"])
    raw = {
        "rows": [
            {"keys": ["dup query", "https://example.com/a/"],
             "position": 15, "impressions": 500, "clicks": 1, "ctr": 0.002},
            {"keys": ["dup query", "https://example.com/b/"],
             "position": 18, "impressions": 300, "clicks": 0, "ctr": 0.0},
        ]
    }
    candidates = discover(raw, inv)
    assert len(candidates) == 1
