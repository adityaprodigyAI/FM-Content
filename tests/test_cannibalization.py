"""Tests for tools/cannibalization.py.

The most important test in the whole repo is `test_w20_regression`:
the exact slate proposal that slipped through the v5 pipeline must be
hard-blocked here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from tools.cannibalization import (
    CannibalizationError,
    ProposedTopic,
    evaluate,
    evaluate_or_block,
)
from tools.inventory import (
    DegradedInventoryError,
    Inventory,
    PublishedPost,
    StaleInventoryError,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stale_iso() -> str:
    from datetime import timedelta
    return (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()


def _well_formed_inventory(extra: list[PublishedPost] | None = None) -> Inventory:
    posts: list[PublishedPost] = [
        PublishedPost(
            id=70001,
            slug="ai-consulting-cost-2026",
            title="How Much Does AI Consulting Cost in 2026?",
            url="https://firstmovers.ai/ai-consulting-cost-2026/",
            published_at="2026-04-15",
            kind="blog",
            focus_keyword="ai consulting cost",
            organic_keywords=["ai consulting", "ai consultant rates"],
        ),
        PublishedPost(
            id=70002,
            slug="ai-workflow-automation",
            title="AI Workflow Automation: 5 Proven Wins in 30 Days",
            url="https://firstmovers.ai/ai-workflow-automation/",
            published_at="2026-04-18",
            kind="page",
            focus_keyword="ai workflow automation",
            organic_keywords=[],
        ),
        PublishedPost(
            id=70003,
            slug="resource-based-economy",
            title="What is a Resource Based Economy?",
            url="https://firstmovers.ai/resource-based-economy/",
            published_at="2025-12-12",
            kind="page",
            focus_keyword="resource based economy",
            organic_keywords=[],
        ),
    ]
    if extra:
        posts.extend(extra)
    return Inventory(posts=posts, generated_at=_now_iso())


# ---------- W20 regression — the load-bearing test ----------


def test_w20_regression_resource_based_economy_blocked():
    """
    The exact W20 slate proposal that v5 marked 'clear' even though the URL
    already existed at firstmovers.ai/resource-based-economy/.

    Source: data/content/runs/_title-slates/2026-W20.json (firstmover-hub),
    proposal #3, GSC striking-distance evidence cited the same URL.

    This MUST be blocked at severity=critical.
    """
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="resource-based-economy",
        title="What a Resource Based Economy Means for AI Operators in 2026",
        focus_keyword="resource based economy",
        category_id=13,
        audience="diy",
        canonical_url="https://firstmovers.ai/resource-based-economy/",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical", (
        f"W20 regression: expected critical, got {verdict.severity}. "
        f"Matches: {[m.reason for m in verdict.matches]}"
    )
    assert verdict.recommended_action == "block"
    # Should match BOTH the slug (Rule 1) AND the focus keyword (Rule 2)
    reasons = " | ".join(m.reason for m in verdict.matches)
    assert "slug exact match" in reasons
    assert "focus_keyword" in reasons.lower()


def test_w20_regression_blocks_via_evaluate_or_block():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="resource-based-economy",
        title="...",
        focus_keyword="resource based economy",
        category_id=13,
        audience="diy",
    )
    with pytest.raises(CannibalizationError):
        evaluate_or_block(topic, inv)


# ---------- Rule 1: slug / URL exact match ----------


def test_rule1_slug_exact_match_is_critical():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="ai-consulting-cost-2026",
        title="A totally different title",
        focus_keyword="something else entirely",
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical"


def test_rule1_canonical_url_match_is_critical():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="some-other-slug",
        title="Different title",
        focus_keyword="different keyword",
        category_id=27,
        audience="done-for-you",
        canonical_url="https://firstmovers.ai/ai-consulting-cost-2026/",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical"


def test_rule1_normalizes_slug_case_and_underscores():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="AI_Consulting_Cost_2026",
        title="...",
        focus_keyword="x",
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical"


# ---------- Rule 2: focus keyword exact match ----------


def test_rule2_focus_kw_exact_match_against_focus_kw_is_critical():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="totally-different-slug",
        title="Different",
        focus_keyword="ai consulting cost",
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical"


def test_rule2_focus_kw_exact_match_against_organic_kw_is_critical():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="totally-different-slug",
        title="Different",
        focus_keyword="ai consultant rates",  # appears as organic kw on post #70001
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical"


def test_rule2_normalizes_dashes_and_underscores():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="totally-different",
        title="Different",
        focus_keyword="ai-consulting_cost",
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical"


# ---------- Rule 3: title token-set Jaccard ----------


def test_rule3_title_jaccard_high_is_high_severity():
    """A near-identical title (just appending one extra word) hits the
    Jaccard >= 0.7 threshold."""
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="ai-consulting-pricing",
        title="How Much Does AI Consulting Cost in 2026?",  # identical except slug differs
        focus_keyword="ai consulting pricing",
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    # Title is identical to existing post -> Jaccard=1.0 -> high
    # focus_keyword "ai consulting pricing" bigrams: {"ai consulting", "consulting pricing"}
    # vs post "ai consulting cost" bigrams: {"ai consulting", "consulting cost"}
    # Overlap = 1/3 ~= 0.33, below medium threshold
    assert verdict.severity in ("high", "critical"), f"got {verdict.severity}"


def test_rule3_jaccard_below_threshold_is_not_blocking():
    """A topic with only modest title overlap should NOT be blocked.

    The conservative threshold is intentional — we don't want false positives
    that consume Nikki's review attention on legitimately different angles.
    """
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="ai-implementation-stalls-roadmap",
        title="Why AI Implementations Stall: A 2026 Recovery Roadmap",
        focus_keyword="ai implementation recovery",
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    # Block (critical/high) only when truly duplicative; everything else passes
    assert verdict.severity not in ("critical", "high"), (
        f"unexpected block: {verdict.severity} {verdict.matches}"
    )


# ---------- Rule 4: focus-kw n-gram overlap ----------


def test_rule4_dense_ngram_overlap_blocks_high():
    """Topic focus_kw shares 2 of 3 bigrams with an existing post's
    focus_kw -> Rule 4 fires at high severity.

    Topic FK bigrams: {ai consulting, consulting cost, cost guide}
    Post  FK bigrams: {ai consulting, consulting cost}              (post #70001)
    Intersection = 2; union = 3; Jaccard = 0.66 -> high.
    """
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="ai-consulting-cost-guide-2026",
        title="Picking an AI Consultant in 2026",
        focus_keyword="ai consulting cost guide",
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    # Rule 4 should fire at high (>= 0.5 Jaccard), or critical via Rule 2 if
    # the substring "ai consulting cost" matches more strictly. Either way
    # the topic must be blocked.
    assert verdict.severity in ("high", "critical"), f"got {verdict.severity}"


# ---------- Clear case ----------


def test_unrelated_topic_is_clear():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="prompt-engineering-for-customer-support",
        title="Prompt Engineering for Customer Support Teams",
        focus_keyword="prompt engineering customer support",
        category_id=29,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "clear"
    assert verdict.recommended_action == "proceed"


# ---------- Structural defenses ----------


def test_evaluate_refuses_stale_inventory():
    posts = [
        PublishedPost(
            id=1, slug="x", title="X", url="https://firstmovers.ai/x/",
            published_at="2026-01-01", kind="blog",
            focus_keyword="x kw", organic_keywords=["k1"],
        ),
    ]
    inv = Inventory(posts=posts, generated_at=_stale_iso())
    topic = ProposedTopic(
        slug="y", title="Y", focus_keyword="y", category_id=27, audience="diy",
    )
    with pytest.raises(StaleInventoryError):
        evaluate(topic, inv)


def test_evaluate_refuses_degraded_inventory():
    """The W20 bug origin: a degraded snapshot (focus_keyword=None) MUST
    cause the gate to refuse to run, not silently fail-open to 'clear'."""
    posts = [
        PublishedPost(
            id=1, slug="x", title="X", url="https://firstmovers.ai/x/",
            published_at="2026-04-01", kind="blog",
            focus_keyword=None,  # the bug
            organic_keywords=[],
        ),
    ]
    inv = Inventory(posts=posts, generated_at=_now_iso())
    topic = ProposedTopic(
        slug="y", title="Y", focus_keyword="y kw", category_id=27, audience="diy",
    )
    with pytest.raises(DegradedInventoryError):
        evaluate(topic, inv)


# ---------- Top matches surface ----------


def test_verdict_includes_top_matches():
    inv = _well_formed_inventory()
    topic = ProposedTopic(
        slug="ai-consulting-cost-2026",  # critical match
        title="How Much Does AI Consulting Cost in 2026?",  # also Jaccard match
        focus_keyword="ai consulting cost",  # also focus-kw match
        category_id=27,
        audience="done-for-you",
    )
    verdict = evaluate(topic, inv)
    assert verdict.severity == "critical"
    assert len(verdict.matches) >= 2
