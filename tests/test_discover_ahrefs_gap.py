"""Tests for tools/discover/ahrefs_gap.py."""

from __future__ import annotations

from datetime import datetime, timezone

from tools.discover.ahrefs_gap import (
    _competitor_brand_stem,
    _has_ai_marker,
    discover,
)
from tools.inventory import Inventory, PublishedPost


def _inv() -> Inventory:
    return Inventory(
        posts=[
            PublishedPost(
                id=1, slug="ai-consulting",
                title="AI Consulting",
                url="https://firstmovers.ai/ai-consulting/",
                published_at="2026-04-01", kind="blog",
                focus_keyword="ai consulting",
                organic_keywords=["ai consultant rates"],
            ),
        ],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------- core flow ----------


def test_keeps_ai_relevant_keyword_with_volume_under_max_kd():
    raw = {"keywords": [
        {"keyword": "agentic ai for sales", "volume": 800, "difficulty": 30},
    ]}
    cands = discover("hubspot.com", raw, _inv())
    assert len(cands) == 1
    assert cands[0].focus_keyword == "agentic ai for sales"
    assert cands[0].discovery_source == "ahrefs_competitor_gap"
    assert cands[0].discovery_id.startswith("ahrefs:hubspot.com:")


# ---------- competitor brand filter ----------


def test_drops_competitor_brand_keywords():
    """The W21-style noise — competitor's own brand queries."""
    raw = {"keywords": [
        {"keyword": "hubspot", "volume": 489000, "difficulty": 60},
        {"keyword": "hubspot login", "volume": 114000, "difficulty": 48},
        {"keyword": "hubspot academy", "volume": 28000, "difficulty": 25},
        {"keyword": "hubspot pricing", "volume": 15000, "difficulty": 57},
    ]}
    cands = discover("hubspot.com", raw, _inv())
    assert cands == []


def test_competitor_stem_extraction():
    assert _competitor_brand_stem("hubspot.com") == "hubspot"
    assert _competitor_brand_stem("www.mckinsey.com") == "mckinsey"
    assert _competitor_brand_stem("https://www.deloitte.com/us") == "deloitte"
    assert _competitor_brand_stem("") == ""


# ---------- AI relevance filter ----------


def test_drops_non_ai_keywords():
    """Generic competitor rankings without AI relevance."""
    raw = {"keywords": [
        {"keyword": "tam sam som", "volume": 15000, "difficulty": 13},
        {"keyword": "como aprender programacion", "volume": 110000, "difficulty": 0},
        {"keyword": "follow up email", "volume": 8400, "difficulty": 11},
    ]}
    cands = discover("competitor.com", raw, _inv())
    assert cands == [], (
        f"Non-AI keywords leaked through: {[c.focus_keyword for c in cands]}"
    )


def test_keeps_ai_relevant_terms():
    """Whole list of AI-marker variants."""
    raw = {"keywords": [
        {"keyword": "ai workflow automation", "volume": 1000, "difficulty": 30},
        {"keyword": "best gpt prompts for sales", "volume": 500, "difficulty": 20},
        {"keyword": "agentic systems for ops", "volume": 200, "difficulty": 15},
        {"keyword": "claude vs chatgpt for marketing", "volume": 800, "difficulty": 25},
    ]}
    cands = discover("competitor.com", raw, _inv())
    assert len(cands) == 4


def test_ai_marker_word_boundary():
    """'rail' must NOT match 'ai' — word boundaries enforced."""
    assert _has_ai_marker("ai consulting") is True
    assert _has_ai_marker("rail transport") is False
    assert _has_ai_marker("airbnb host") is False  # 'ai' is a substring but not a word
    assert _has_ai_marker("said yes") is False


def test_require_ai_relevance_can_be_disabled():
    """For non-AI niches, set require_ai_relevance=False."""
    raw = {"keywords": [
        {"keyword": "generic business term", "volume": 1000, "difficulty": 20},
    ]}
    cands = discover("competitor.com", raw, _inv(), require_ai_relevance=False)
    assert len(cands) == 1


# ---------- inventory dedupe ----------


def test_drops_keywords_already_in_inventory():
    raw = {"keywords": [
        {"keyword": "ai consulting", "volume": 1000, "difficulty": 30},  # we have it
        {"keyword": "ai consultant rates", "volume": 500, "difficulty": 20},  # organic kw
        {"keyword": "ai workflow design", "volume": 800, "difficulty": 25},  # new — keep
    ]}
    cands = discover("competitor.com", raw, _inv())
    fks = [c.focus_keyword for c in cands]
    assert "ai consulting" not in fks
    assert "ai consultant rates" not in fks
    assert "ai workflow design" in fks


# ---------- demand floor + KD ceiling ----------


def test_drops_low_volume_keywords():
    raw = {"keywords": [
        {"keyword": "obscure ai topic", "volume": 10, "difficulty": 20},
    ]}
    cands = discover("competitor.com", raw, _inv())
    assert cands == []


def test_drops_high_kd_keywords():
    raw = {"keywords": [
        {"keyword": "ai", "volume": 1000000, "difficulty": 95},
    ]}
    cands = discover("competitor.com", raw, _inv())
    assert cands == []


# ---------- top_n ----------


def test_respects_top_n():
    raw = {"keywords": [
        {"keyword": f"ai topic {i}", "volume": 500, "difficulty": 30}
        for i in range(20)
    ]}
    cands = discover("competitor.com", raw, _inv(), top_n=5)
    assert len(cands) == 5
