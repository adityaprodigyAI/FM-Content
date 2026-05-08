"""Tests for tools/discover/ga4_gap.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from tools.discover.ga4_gap import discover
from tools.inventory import Inventory, PublishedPost


def _inv(slugs: list[str]) -> Inventory:
    return Inventory(
        posts=[
            PublishedPost(
                id=1000 + i,
                slug=slug,
                title=slug,
                url=f"https://firstmovers.ai/{slug}/",
                published_at="2026-04-01",
                kind="page" if "page" in slug or "consulting" in slug else "blog",
                focus_keyword=slug.replace("-", " "),
                organic_keywords=["x"] if "blog" in slug or "page" not in slug else [],
            )
            for i, slug in enumerate(slugs)
        ],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def test_emits_companion_post_for_rising_page():
    inv = _inv(["consulting"])
    raw = {
        "rows": [
            {"pagePath": "/consulting/", "sessions": 800, "prior_sessions": 400},
        ]
    }
    candidates = discover(raw, inv)
    assert len(candidates) == 1
    c = candidates[0]
    assert c.focus_keyword == "consulting explained"
    assert "companion" in c.rationale.lower() or "cluster" in c.rationale.lower()
    assert c.discovery_source == "ga4_high_traffic_gap"


def test_drops_pages_below_min_sessions():
    inv = _inv(["consulting"])
    raw = {"rows": [
        {"pagePath": "/consulting/", "sessions": 50, "prior_sessions": 20},
    ]}
    assert discover(raw, inv) == []


def test_drops_flat_or_declining_pages():
    inv = _inv(["consulting"])
    raw = {"rows": [
        {"pagePath": "/consulting/", "sessions": 500, "prior_sessions": 600},
    ]}
    assert discover(raw, inv) == []


def test_drops_pages_whose_companion_slug_already_exists():
    inv = _inv(["consulting", "consulting-explained"])
    raw = {"rows": [
        {"pagePath": "/consulting/", "sessions": 800, "prior_sessions": 400},
    ]}
    # companion would be `consulting-explained` but it's already in inventory
    assert discover(raw, inv) == []


def test_handles_mcp_text_wrapper():
    inv = _inv(["x-page"])
    raw = [{"type": "text", "text": json.dumps({"rows": [
        {"pagePath": "/x-page/", "sessions": 500, "prior_sessions": 300},
    ]})}]
    candidates = discover(raw, inv)
    assert len(candidates) == 1


def test_provenance_includes_path_and_growth():
    inv = _inv(["consulting"])
    raw = {"rows": [
        {"pagePath": "/consulting/", "sessions": 800, "prior_sessions": 400},
    ]}
    c = discover(raw, inv)[0]
    assert c.discovery_id == "ga4:consulting"
    assert c.discovery_evidence["sessions"] == 800
    assert c.discovery_evidence["prior_sessions"] == 400
    assert c.discovery_evidence["page_path"] == "/consulting/"
