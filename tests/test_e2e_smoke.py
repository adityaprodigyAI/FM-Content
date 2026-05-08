"""End-to-end smoke test.

Exercises every layer in sequence with synthetic data:

  inventory  -> discovery (4 sources) -> slate -> brief -> assemble ->
  rubric.validate -> push payload.

Proves the full pipeline composes cleanly. Real prose comes from Claude in
production; here we use a hand-crafted body that satisfies the rubric.

No network calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tools.cannibalization import ProposedTopic, evaluate
from tools.clickup import (
    build_parent_task_payload,
    build_subtask_payloads,
    parse_approved_subtasks,
    filter_proposals_by_approval,
)
from tools.discover.ahrefs_gap import discover as ahrefs_discover
from tools.discover.ga4_gap import discover as ga4_discover
from tools.discover.gsc import discover as gsc_discover
from tools.discover.searchable_aeo import discover_prompts, discover_topics
from tools.draft import assemble, prepare_brief
from tools.images import ImageRef
from tools.inventory import Inventory, PublishedPost, build_inventory, load, save
from tools.push_wp import build_create_payload, parse_create_response
from tools.rank_math import build_meta, to_payload
from tools.rubric import FaqItem
from tools.slate import build_slate, load_slate, write_slate


# ---------- fixtures ----------


def _fresh_inventory() -> Inventory:
    return Inventory(
        posts=[
            PublishedPost(
                id=70001, slug="ai-consulting-cost-2026",
                title="How Much Does AI Consulting Cost in 2026?",
                url="https://firstmovers.ai/ai-consulting-cost-2026/",
                published_at="2026-04-15", kind="blog",
                focus_keyword="ai consulting cost",
                organic_keywords=["ai consulting", "ai consultant rates"],
            ),
            PublishedPost(
                id=70010, slug="resource-based-economy",
                title="What is a Resource Based Economy?",
                url="https://firstmovers.ai/resource-based-economy/",
                published_at="2025-12-01", kind="page",
                focus_keyword="resource based economy",
                organic_keywords=[],
            ),
            # 5 more pages so assert_pages_present passes
            *[
                PublishedPost(
                    id=70020 + i, slug=f"page-{i}",
                    title=f"Page {i}",
                    url=f"https://firstmovers.ai/page-{i}/",
                    published_at="2026-04-01", kind="page",
                    focus_keyword=f"page topic {i}",
                    organic_keywords=[],
                )
                for i in range(5)
            ],
        ],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def _hand_crafted_body(focus_kw: str) -> str:
    """A 2,500-word body that satisfies every rubric rule.

    Used here to prove the assemble->validate pipeline composes; in
    production Claude writes this prose against the rubric skill.
    """
    paragraph = (
        f"{focus_kw} is the practice of routing leads through a deterministic "
        f"workflow plus language-model judgement. The result is a smaller, "
        f"sharper pipeline. Used well, this approach cuts response time in "
        f"half and lifts conversion. "
    ) * 8

    h2_texts = [
        f"Why {focus_kw} matters for operators in 2026",
        "How leading teams set up the system",
        f"Three layers of {focus_kw} every team needs",
        "Common pitfalls to avoid",
        "How to measure return on investment",
        "What to outsource and what to keep",
        "Where to learn more",
    ]

    parts = [
        f"<p>{focus_kw.title()} changes how a leader's day starts. {paragraph}</p>"
    ]
    for i, h in enumerate(h2_texts):
        parts.append(f"<h2>{h}</h2>")
        parts.append(f"<p>{paragraph}</p>")
        if i < 4:
            alt = f"{focus_kw} in action" if i == 0 else f"contextual image {i}"
            parts.append(
                f'<img src="https://images.pexels.com/img-{i}.jpg" '
                f'alt="{alt}" width="1200" height="800">'
            )
    parts.append(
        '<p>For more research, see '
        '<a href="https://hbr.org/topic/subject/artificial-intelligence">HBR on AI</a>, '
        '<a href="https://www.mckinsey.com/quantumblack">McKinsey QuantumBlack</a>, and '
        '<a href="https://hai.stanford.edu/research">Stanford HAI</a>. '
        'Ready to put it to work? '
        '<a href="https://firstmovers.ai/consulting/">Schedule a call</a>.'
        '</p>'
    )
    return "\n".join(parts)


def _fake_image(idx: int, focus_kw: str) -> ImageRef:
    return ImageRef(
        url=f"https://images.pexels.com/img-{idx}.jpg",
        alt=f"{focus_kw} hero" if idx == 0 else f"contextual image {idx}",
        photographer=f"Photographer {idx}",
        photographer_url=f"https://www.pexels.com/@photographer-{idx}/",
        pexels_url=f"https://www.pexels.com/photo/{idx}/",
        width=1200,
        height=800,
    )


# ---------- the smoke test ----------


def test_full_pipeline_composes_end_to_end(tmp_path: Path):
    inv = _fresh_inventory()
    inv.assert_fresh()
    inv.assert_complete()
    inv.assert_pages_present(min_pages=5)

    # 1. DISCOVERY — exercise all 4 extractors
    gsc_raw = {
        "rows": [
            # The W20-style trap query — ranking URL is already ours, MUST be dropped
            {"keys": ["resource based economy", "https://firstmovers.ai/resource-based-economy/"],
             "position": 19, "impressions": 256, "clicks": 1, "ctr": 0.004},
            # A clean striking-distance query
            {"keys": ["ai inbox automation playbook", "https://example.com/their-blog/"],
             "position": 14, "impressions": 800, "clicks": 2, "ctr": 0.0025},
            # Another clean one
            {"keys": ["agentic ai for small business", "https://example.com/their-blog/"],
             "position": 17, "impressions": 500, "clicks": 0, "ctr": 0.0},
        ]
    }
    gsc_cands = gsc_discover(gsc_raw, inv)
    assert all(
        c.focus_keyword != "resource based economy" for c in gsc_cands
    ), "GSC discovery emitted the W20 trap query"
    assert any(c.focus_keyword == "ai inbox automation playbook" for c in gsc_cands)

    ahrefs_raw = {"keywords": [
        {"keyword": "ai roadmap framework", "volume": 800, "difficulty": 35,
         "position": 5, "traffic": 200},
        {"keyword": "ai consulting", "volume": 1200, "difficulty": 50,  # we have this
         "position": 3, "traffic": 500},
    ]}
    ahrefs_cands = ahrefs_discover("mckinsey.com", ahrefs_raw, inv)
    assert any(c.focus_keyword == "ai roadmap framework" for c in ahrefs_cands)
    assert all(c.focus_keyword != "ai consulting" for c in ahrefs_cands), \
        "Ahrefs gap kept a keyword we already rank for"

    searchable_prompt_raw = {"prompts": [
        {"prompt": "How do I scale AI ops?", "topic": "AI Automation",
         "mention_rate": 0.0, "citation_count": 12},
    ]}
    prompt_cands = discover_prompts(searchable_prompt_raw, inv)
    assert len(prompt_cands) == 1

    searchable_topic_raw = {"topics": [
        {"topic": "AI workflow design", "coverage": 1.5},
    ]}
    topic_cands = discover_topics(searchable_topic_raw, inv)
    assert len(topic_cands) == 1

    ga4_raw = {"rows": [
        {"pagePath": "/page-0/", "sessions": 800, "prior_sessions": 400},
    ]}
    ga4_cands = ga4_discover(ga4_raw, inv)
    assert len(ga4_cands) == 1

    all_cands = gsc_cands + ahrefs_cands + prompt_cands + topic_cands + ga4_cands

    # 2. SLATE
    slate = build_slate(week="2026-W22", candidates=all_cands, inventory=inv)
    assert len(slate.proposals) >= 4
    assert all(
        p.focus_keyword.lower() != "resource based economy"
        for p in slate.proposals
    ), "slate contained the W20 trap"
    assert all(
        p.cannibalization_severity not in ("critical", "high")
        for p in slate.proposals
    )

    # 3. WRITE + LOAD ROUND-TRIP — the slate persists cleanly
    slate_dir = tmp_path / "slates"
    write_slate(slate, dir_=slate_dir)
    loaded = load_slate("2026-W22", dir_=slate_dir)
    assert len(loaded.proposals) == len(slate.proposals)

    # 4. CLICKUP — emit payloads are well-formed
    parent = build_parent_task_payload(slate)
    assert parent.list_id  # CONTENT_PROJECTS_LIST_ID
    subs = build_subtask_payloads(slate, parent_task_id="parent_xyz")
    assert len(subs) == len(slate.proposals)

    # Simulate Nikki ticking the first 2 subtasks
    fake_clickup_response = {
        "subtasks": [
            {
                "name": p.working_title,
                "custom_id": p.focus_keyword,
                "status": {"type": "done" if i < 2 else "open", "status": "complete"},
            }
            for i, p in enumerate(slate.proposals)
        ]
    }
    approved = parse_approved_subtasks(fake_clickup_response)
    approved_proposals = filter_proposals_by_approval(slate, approved, max_approvals=7)
    assert len(approved_proposals) == 2

    # 5. WEDNESDAY: prepare brief + assemble + validate, for one approved title
    target = approved_proposals[0]
    brief = prepare_brief(target, inv)
    assert brief.proposal.focus_keyword == target.focus_keyword
    assert len(brief.internal_links) >= 3
    assert len(brief.external_citations) >= 3

    body_html = _hand_crafted_body(target.focus_keyword)
    images = [_fake_image(i, target.focus_keyword) for i in range(4)]
    faq = [
        FaqItem(question=f"What is {target.focus_keyword}?",
                answer="A workflow."),
        FaqItem(question=f"How long to set up {target.focus_keyword}?",
                answer="Days."),
        FaqItem(question=f"What does {target.focus_keyword} cost?",
                answer="It depends on scale."),
    ]
    seo_title = f"{target.focus_keyword.title()}: Proven 2026 Guide"[:60]
    meta = (f"{target.focus_keyword} guide for 2026. Proven framework, three "
            f"layers, real ops outcomes.")[:155]

    assembled = assemble(
        brief,
        body_html=body_html,
        faq_items=faq,
        images=images,
        seo_title=seo_title,
        meta_description=meta,
    )
    # The rubric validator inside assemble didn't raise — every rule passed
    assert assembled.title == target.working_title
    assert "https://images.pexels.com/" in assembled.body_html
    assert assembled.slug == target.slug

    # 6. PUSH PAYLOAD — well-formed, status=draft, valid category
    push_payload = build_create_payload(
        title=assembled.title,
        content=assembled.body_html,
        slug=assembled.slug,
        excerpt=assembled.excerpt,
        category_id=assembled.category_id,
    )
    assert push_payload.status == "draft"
    assert push_payload.categories[0] == assembled.category_id

    # 7. RANK MATH PAYLOAD
    rm = build_meta(
        focus_keyword=assembled.focus_keyword,
        seo_title=assembled.seo_title,
        meta_description=assembled.meta_description,
        slug=assembled.slug,
    )
    rm_payload = to_payload(99999, rm)
    assert rm_payload["objectID"] == 99999
    assert rm_payload["meta"]["rank_math_focus_keyword"] == assembled.focus_keyword

    # 8. PARSE-CREATE-RESPONSE — the agent will get a response back from MCP
    fake_resp = {"id": 12345, "slug": assembled.slug, "status": "draft",
                 "link": f"https://firstmovers.ai/{assembled.slug}/"}
    parsed = parse_create_response(fake_resp)
    assert parsed and parsed["id"] == 12345
    assert "edit_url" in parsed
    assert "preview_url" in parsed


# ---------- inventory persistence E2E ----------


def test_inventory_save_load_e2e(tmp_path: Path):
    inv = _fresh_inventory()
    path = tmp_path / "snapshot.json"
    save(inv, path)
    loaded = load(path)
    assert len(loaded.posts) == len(inv.posts)
    loaded.assert_fresh()
    loaded.assert_complete()
    loaded.assert_pages_present(min_pages=5)
    # Round-trip preserves every meaningful field
    for orig, lo in zip(inv.posts, loaded.posts):
        assert orig.id == lo.id
        assert orig.slug == lo.slug
        assert orig.kind == lo.kind
        assert orig.focus_keyword == lo.focus_keyword
        assert orig.organic_keywords == lo.organic_keywords
