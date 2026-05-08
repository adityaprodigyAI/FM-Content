"""Tests for tools/discover/searchable_aeo.py."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from tools.discover.searchable_aeo import discover_prompts, discover_topics
from tools.inventory import Inventory, PublishedPost


def _inv() -> Inventory:
    return Inventory(
        posts=[
            PublishedPost(
                id=1, slug="ai-inbox-automation",
                title="AI Inbox Automation",
                url="https://firstmovers.ai/ai-inbox-automation/",
                published_at="2026-04-01", kind="blog",
                focus_keyword="ai inbox automation",
                organic_keywords=["inbox triage"],
            ),
        ],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------- discover_prompts ----------


def test_emits_zero_mention_high_citation_prompts():
    raw = {
        "prompts": [
            {"prompt": "What is agentic AI for sales?", "topic": "AI Sales",
             "mention_rate": 0.0, "citation_count": 12},
            {"prompt": "How does AI inbox automation work?", "topic": "AI Automation",
             "mention_rate": 5.0, "citation_count": 20},  # we have coverage
            {"prompt": "Niche prompt nobody asks", "topic": "Other",
             "mention_rate": 0.0, "citation_count": 2},  # too few citations
        ]
    }
    candidates = discover_prompts(raw, _inv())
    assert len(candidates) == 1
    assert candidates[0].focus_keyword == "what is agentic ai for sales?"
    assert candidates[0].discovery_source == "searchable_prompt"


def test_drops_prompts_already_in_inventory_focus_keywords():
    raw = {
        "prompts": [
            {"prompt": "ai inbox automation", "topic": "x",
             "mention_rate": 0.0, "citation_count": 100},
        ]
    }
    candidates = discover_prompts(raw, _inv())
    assert candidates == []


def test_handles_mcp_text_wrapper():
    raw = [{"type": "text", "text": json.dumps({"prompts": [
        {"prompt": "fresh question", "topic": "x",
         "mention_rate": 0.0, "citation_count": 10},
    ]})}]
    candidates = discover_prompts(raw, _inv())
    assert len(candidates) == 1


def test_emits_provenance_with_full_evidence():
    raw = {"prompts": [
        {"prompt": "fresh prompt", "topic": "AI Tools",
         "mention_rate": 0.0, "citation_count": 8},
    ]}
    candidates = discover_prompts(raw, _inv())
    c = candidates[0]
    assert c.discovery_id.startswith("searchable_prompt:")
    assert c.discovery_evidence["citation_count"] == 8
    assert c.discovery_evidence["topic"] == "AI Tools"


# ---------- discover_topics ----------


def test_emits_low_coverage_topics():
    raw = {
        "topics": [
            {"topic": "AI Workflow Automation", "coverage": 2.0},   # low — emit
            {"topic": "AI Inbox Triage", "coverage": 8.0},          # above max — drop
        ]
    }
    candidates = discover_topics(raw, _inv())
    assert len(candidates) == 1
    assert candidates[0].focus_keyword == "ai workflow automation"
    assert candidates[0].discovery_source == "searchable_competitor_topic"


def test_topics_dedupe_against_inventory():
    raw = {"topics": [
        {"topic": "ai inbox automation", "coverage": 1.0},
    ]}
    candidates = discover_topics(raw, _inv())
    assert candidates == []
