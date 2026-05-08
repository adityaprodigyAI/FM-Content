"""Tests for tools/rubric.py.

Covers each validator individually plus the validate() entry point.
"""

from __future__ import annotations

import pytest

from tools.rubric import (
    Draft,
    FaqItem,
    RubricViolation,
    validate,
)


def _good_body() -> str:
    """A 2,500-word body with 7 H2s, 3 external dofollow links, focus_kw in
    lede + ≥1 H2. v1 ships text-only — no <img> tags. Used as the baseline
    for fault-injection tests.
    """
    h2_texts = [
        "Why ai inbox automation matters now",
        "How operators set up the system",
        "The three layers of inbox triage",
        "Common pitfalls to avoid",
        "How to measure return on investment",
        "What to outsource and what to keep",
        "Where to learn more",
    ]
    paragraph = (
        "AI inbox automation is the practice of routing email through deterministic "
        "logic and language models so the inbox reads itself. The result is a "
        "smaller, more focused queue and a more responsive operator. Used well, "
        "it cuts daily email time in half. "
    ) * 8  # ~150 words

    parts = []
    parts.append(f"<p>AI inbox automation changes how a leader's day starts. {paragraph}</p>")
    for h in h2_texts:
        parts.append(f"<h2>{h}</h2>")
        parts.append(f"<p>{paragraph}</p>")
    parts.append(
        '<p>For more, see '
        '<a href="https://hbr.org/topic/ai">HBR</a>, '
        '<a href="https://www.mckinsey.com/quantumblack">McKinsey</a>, and '
        '<a href="https://hai.stanford.edu/research">Stanford HAI</a>. '
        'Ready to put it to work? Schedule a call at '
        '<a href="https://firstmovers.ai/consulting/">firstmovers.ai/consulting/</a>.'
        '</p>'
    )
    return "\n".join(parts)


def _good_draft(**overrides) -> Draft:
    base = dict(
        title="AI Inbox Automation: A Proven 2026 Operating Guide",
        seo_title="AI Inbox Automation: Proven 2026 Guide",
        meta_description="AI inbox automation in 2026 - proven 3-layer system to cut email time. Step-by-step guide for ops leaders.",
        focus_keyword="ai inbox automation",
        slug="ai-inbox-automation-guide-2026",
        category_id=28,
        audience="done-for-you",
        body_html=_good_body(),
        faq_items=[
            FaqItem(question="What is ai inbox automation?", answer="A workflow."),
            FaqItem(question="How long to set up?", answer="Days."),
            FaqItem(question="What does it cost?", answer="$25K-60K range."),
        ],
        image_alts=[],  # v1 ships text-only
    )
    base.update(overrides)
    return Draft(**base)


# ---------- happy path ----------


def test_validate_passes_well_formed_draft():
    validate(_good_draft())


# ---------- title rules ----------


def test_title_with_trailing_period_fails():
    with pytest.raises(RubricViolation, match="title"):
        validate(_good_draft(title="A Proven Guide."))


def test_title_with_em_dash_fails():
    with pytest.raises(RubricViolation, match="title"):
        validate(_good_draft(title="AI Inbox Automation — A Proven Guide"))


def test_title_too_long_fails():
    long = "AI Inbox Automation: " + "x" * 200
    with pytest.raises(RubricViolation, match="title"):
        validate(_good_draft(title=long))


# ---------- seo_title rules ----------


def test_seo_title_too_long_fails():
    long = "AI Inbox Automation: " + "x" * 100
    with pytest.raises(RubricViolation):
        validate(_good_draft(seo_title=long))


def test_seo_title_without_focus_keyword_fails():
    with pytest.raises(RubricViolation, match="seo_title_focus_keyword"):
        validate(_good_draft(seo_title="A Proven 2026 Guide"))


def test_seo_title_without_power_word_fails():
    with pytest.raises(RubricViolation, match="seo_title_power_word"):
        validate(_good_draft(seo_title="AI Inbox Automation 2026 Information"))


# ---------- meta_description ----------


def test_meta_description_too_long_fails():
    long = "x" * 300
    with pytest.raises(RubricViolation, match="meta_description"):
        validate(_good_draft(meta_description=long))


def test_meta_description_without_focus_keyword_fails():
    with pytest.raises(RubricViolation, match="meta_description_focus_keyword"):
        validate(_good_draft(meta_description="A guide to email triage in 2026."))


# ---------- slug ----------


def test_slug_must_contain_focus_keyword():
    with pytest.raises(RubricViolation, match="slug_focus_keyword"):
        validate(_good_draft(slug="something-totally-different-2026"))


def test_invalid_slug_format_fails():
    with pytest.raises(RubricViolation, match="slug"):
        validate(_good_draft(slug="UPPER-CASE"))


# ---------- word count ----------


def test_short_body_fails_word_count():
    short = "<p>too short</p>" * 5
    with pytest.raises(RubricViolation, match="word_count"):
        validate(_good_draft(body_html=short))


# ---------- H2 ----------


def test_too_few_h2_fails():
    body = _good_body().replace("<h2>", "<h3>").replace("</h2>", "</h3>")
    with pytest.raises(RubricViolation, match="h2_count"):
        validate(_good_draft(body_html=body))


def test_no_h2_with_focus_keyword_fails():
    body = _good_body()
    # Replace every H2 text with something that doesn't contain focus_kw
    import re
    body_no_kw = re.sub(
        r"<h2[^>]*>.*?</h2>",
        lambda _: "<h2>An unrelated heading</h2>",
        body, flags=re.DOTALL,
    )
    with pytest.raises(RubricViolation, match="h2_focus_keyword"):
        validate(_good_draft(body_html=body_no_kw))


# ---------- H1 ----------


def test_h1_in_body_fails():
    body = "<h1>A leading h1</h1>\n" + _good_body()
    with pytest.raises(RubricViolation, match="no_h1_in_body"):
        validate(_good_draft(body_html=body))


# ---------- images (DISABLED in v1) ----------


def test_text_only_body_passes_in_v1():
    """Body with no <img> tags is valid in v1 (text-only mode)."""
    body = _good_body()
    assert "<img" not in body
    validate(_good_draft(body_html=body))


def test_text_only_body_with_empty_image_alts_passes():
    """No image_alts list is fine when MIN_IMAGE_COUNT is 0."""
    validate(_good_draft(image_alts=[]))


# ---------- external links ----------


def test_too_few_external_links_fails():
    body = _good_body().replace("hbr.org", "firstmovers.ai")
    body = body.replace("mckinsey.com", "firstmovers.ai")
    body = body.replace("hai.stanford.edu", "firstmovers.ai")
    with pytest.raises(RubricViolation, match="external_links"):
        validate(_good_draft(body_html=body))


# ---------- forbidden phrases ----------


def test_free_audit_in_body_fails():
    body = _good_body() + "\n<p>Get a free audit today!</p>"
    with pytest.raises(RubricViolation, match="forbidden_phrase"):
        validate(_good_draft(body_html=body))


# ---------- em dashes ----------


def test_em_dash_in_body_fails():
    body = _good_body() + "\n<p>This — that.</p>"
    with pytest.raises(RubricViolation, match="no_em_dashes"):
        validate(_good_draft(body_html=body))


# ---------- affiliate token ----------


def test_affiliate_token_leak_fails():
    body = _good_body() + "\n<p>Try [AFFILIATE_LINK:CLAUDE] today.</p>"
    with pytest.raises(RubricViolation, match="affiliate_token_leak"):
        validate(_good_draft(body_html=body))


# ---------- extra JSON-LD ----------


def test_blogposting_jsonld_in_body_fails():
    body = _good_body() + '<script type="application/ld+json">{"@type":"BlogPosting"}</script>'
    with pytest.raises(RubricViolation, match="extra_jsonld_blogposting"):
        validate(_good_draft(body_html=body))


def test_breadcrumb_jsonld_in_body_fails():
    body = _good_body() + '<script type="application/ld+json">{"@type":"BreadcrumbList"}</script>'
    with pytest.raises(RubricViolation, match="extra_jsonld_breadcrumb"):
        validate(_good_draft(body_html=body))


# ---------- FAQ count ----------


def test_too_few_faq_items_fails():
    with pytest.raises(RubricViolation, match="faq_count"):
        validate(_good_draft(faq_items=[FaqItem(question="?", answer=".")]))


def test_too_many_faq_items_fails():
    items = [FaqItem(question=f"q{i}", answer=f"a{i}") for i in range(15)]
    with pytest.raises(RubricViolation, match="faq_count"):
        validate(_good_draft(faq_items=items))


# ---------- lede focus keyword ----------


def test_lede_without_focus_keyword_fails():
    """Build a body where focus_keyword is absent from the first 10%."""
    # No focus keyword in lede or in the first 2 H2s. Place focus_kw deeper in.
    paragraph = (
        "Email is annoying for many leaders. "
        "Triage is hard, and most ops teams default to manual review. "
        "There are better operating patterns to consider. "
    ) * 80  # plenty of words but no focus_kw
    parts = []
    parts.append(f"<p>{paragraph}</p>")
    h2_texts = [
        "How operators rethink the inbox", "Common pitfalls to avoid",
        "Three layers of triage", "Measuring return on investment",
        "What to outsource and what to keep", "Why ai inbox automation matters",
        "Where to learn more",
    ]
    paragraph2 = (
        "AI inbox automation is the practice of routing email through deterministic "
        "logic and language models. " * 8
    )
    for i, h in enumerate(h2_texts):
        parts.append(f"<h2>{h}</h2>")
        parts.append(f"<p>{paragraph2}</p>")
        if i < 4:
            alt = "ai inbox automation hero" if i == 0 else f"contextual image {i}"
            parts.append(f'<img src="https://example.com/img-{i}.jpg" alt="{alt}" width="1200" height="800">')
    parts.append(
        '<p>See '
        '<a href="https://hbr.org/topic/ai">HBR</a>, '
        '<a href="https://www.mckinsey.com/quantumblack">McKinsey</a>, '
        '<a href="https://hai.stanford.edu/research">Stanford HAI</a>. '
        'Schedule at <a href="https://firstmovers.ai/consulting/">'
        'first movers consulting</a>.</p>'
    )
    body = "\n".join(parts)
    with pytest.raises(RubricViolation, match="lede_focus_keyword"):
        validate(_good_draft(body_html=body))


# ---------- CTA routing ----------


def test_done_for_you_cta_must_link_to_consulting():
    body = _good_body().replace("/consulting/", "/labs/")
    with pytest.raises(RubricViolation, match="cta_routing"):
        validate(_good_draft(body_html=body))


def test_diy_cta_must_link_to_labs():
    # _good_body links to /consulting/ but not /labs/. DIY audience requires /labs/.
    body = _good_body()
    with pytest.raises(RubricViolation, match="cta_routing"):
        validate(_good_draft(audience="diy", body_html=body))


# ---------- category ----------


def test_invalid_category_fails():
    with pytest.raises(RubricViolation, match="category"):
        validate(_good_draft(category_id=999))


# ---------- audience ----------


def test_invalid_audience_fails():
    with pytest.raises(RubricViolation, match="audience"):
        validate(_good_draft(audience="agency"))
