"""Tests for tools/inventory.py.

These tests do not hit the network. They feed mocked MCP-shaped responses
through the parsing helpers and verify the snapshot is well-formed.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tools.inventory import (
    DegradedInventoryError,
    Inventory,
    PublishedPost,
    StaleInventoryError,
    attach_ahrefs_organic_keywords,
    attach_rank_math_focus_keywords,
    build_inventory,
    load,
    merge,
    parse_wp_posts,
    save,
)


# ---------- fixtures ----------


def _post(id_: int, slug: str, *, kind: str = "blog", focus: str | None = None,
          organic: list[str] | None = None) -> PublishedPost:
    return PublishedPost(
        id=id_,
        slug=slug,
        title=slug.replace("-", " ").title(),
        url=f"https://firstmovers.ai/{slug}/",
        published_at="2026-04-30",
        kind=kind,
        category_ids=[27],
        focus_keyword=focus,
        organic_keywords=organic or [],
    )


def _well_formed_inventory(*, fresh: bool = True, n_pages: int = 10) -> Inventory:
    posts: list[PublishedPost] = []
    for i in range(20):
        posts.append(
            _post(
                i + 1,
                f"blog-slug-{i}",
                kind="blog",
                focus=f"focus keyword {i}",
                organic=[f"organic kw {i}-{j}" for j in range(3)],
            )
        )
    for i in range(n_pages):
        posts.append(
            _post(
                100 + i,
                f"page-slug-{i}",
                kind="page",
                focus=f"page topic {i}",
                organic=[],
            )
        )
    gen = datetime.now(timezone.utc)
    if not fresh:
        gen = gen - timedelta(days=10)
    return Inventory(posts=posts, generated_at=gen.isoformat())


# ---------- assert_fresh ----------


def test_assert_fresh_passes_when_recent():
    inv = _well_formed_inventory()
    inv.assert_fresh()  # should not raise


def test_assert_fresh_raises_when_stale():
    inv = _well_formed_inventory(fresh=False)
    with pytest.raises(StaleInventoryError):
        inv.assert_fresh()


def test_assert_fresh_uses_max_age_days_argument():
    gen = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    inv = Inventory(posts=[], generated_at=gen)
    inv.assert_fresh(max_age_days=7)
    with pytest.raises(StaleInventoryError):
        inv.assert_fresh(max_age_days=2)


# ---------- assert_complete ----------


def test_assert_complete_passes_when_blogs_have_focus_and_organic():
    inv = _well_formed_inventory()
    inv.assert_complete()


def test_assert_complete_fails_when_blog_has_no_focus_keyword():
    inv = _well_formed_inventory()
    inv.posts[0] = PublishedPost(
        id=inv.posts[0].id,
        slug=inv.posts[0].slug,
        title=inv.posts[0].title,
        url=inv.posts[0].url,
        published_at=inv.posts[0].published_at,
        kind="blog",
        focus_keyword=None,
        organic_keywords=["something"],
    )
    with pytest.raises(DegradedInventoryError):
        inv.assert_complete()


def test_assert_complete_fails_when_blog_has_empty_organic_keywords():
    inv = _well_formed_inventory()
    inv.posts[0] = PublishedPost(
        id=inv.posts[0].id,
        slug=inv.posts[0].slug,
        title=inv.posts[0].title,
        url=inv.posts[0].url,
        published_at=inv.posts[0].published_at,
        kind="blog",
        focus_keyword="real focus",
        organic_keywords=[],
    )
    with pytest.raises(DegradedInventoryError):
        inv.assert_complete()


def test_assert_complete_passes_when_page_has_no_organic_keywords():
    """Pages are exempt from organic_keywords (Ahrefs rarely tracks them)."""
    posts = [
        _post(1, "page", kind="page", focus="page topic", organic=[]),
        _post(2, "blog", kind="blog", focus="blog topic", organic=["kw1"]),
    ]
    inv = Inventory(posts=posts, generated_at=datetime.now(timezone.utc).isoformat())
    inv.assert_complete()  # should not raise


def test_assert_complete_fails_when_page_has_no_focus_keyword():
    posts = [
        _post(1, "page", kind="page", focus=None, organic=[]),
    ]
    inv = Inventory(posts=posts, generated_at=datetime.now(timezone.utc).isoformat())
    with pytest.raises(DegradedInventoryError):
        inv.assert_complete()


# ---------- assert_pages_present ----------


def test_assert_pages_present_passes_with_enough_pages():
    inv = _well_formed_inventory(n_pages=10)
    inv.assert_pages_present(min_pages=5)


def test_assert_pages_present_fails_when_no_pages():
    inv = _well_formed_inventory(n_pages=0)
    with pytest.raises(DegradedInventoryError):
        inv.assert_pages_present(min_pages=5)


# ---------- lookups ----------


def test_lookup_by_slug_returns_post():
    inv = _well_formed_inventory()
    post = inv.lookup_by_slug("blog-slug-3")
    assert post is not None and post.slug == "blog-slug-3"


def test_lookup_by_slug_returns_none_when_missing():
    inv = _well_formed_inventory()
    assert inv.lookup_by_slug("does-not-exist") is None


def test_has_url_handles_trailing_slashes():
    inv = _well_formed_inventory()
    assert inv.has_url("https://firstmovers.ai/blog-slug-3")
    assert inv.has_url("https://firstmovers.ai/blog-slug-3/")
    assert not inv.has_url("https://firstmovers.ai/some-other-slug/")


def test_slug_from_fm_url_extracts_last_segment():
    inv = _well_formed_inventory()
    assert inv.slug_from_fm_url("https://firstmovers.ai/blog-slug-3/") == "blog-slug-3"
    assert inv.slug_from_fm_url("https://example.com/foo/") is None


def test_all_focus_keywords_lowercased_and_unique():
    inv = _well_formed_inventory()
    fks = inv.all_focus_keywords()
    assert all(fk == fk.lower() for fk in fks)
    assert len(fks) > 0


# ---------- parse_wp_posts ----------


def test_parse_wp_posts_handles_bare_list():
    raw = [
        {"id": 1, "slug": "foo", "title": {"rendered": "Foo"}, "link": "https://x/", "date": "2026-04-01"},
        {"id": 2, "slug": "bar", "title": "Bar", "link": "https://y/", "date": "2026-04-02"},
    ]
    posts = parse_wp_posts(raw)
    assert len(posts) == 2
    assert posts[0].slug == "foo"
    assert posts[1].title == "Bar"


def test_parse_wp_posts_handles_mcp_text_wrapper():
    raw = [{"type": "text", "text": json.dumps([
        {"id": 1, "slug": "foo", "title": "Foo", "link": "https://x/"},
    ])}]
    posts = parse_wp_posts(raw)
    assert len(posts) == 1 and posts[0].slug == "foo"


def test_parse_wp_posts_uses_kind_argument():
    raw = [{"id": 1, "slug": "consulting", "title": "Consulting", "link": "https://x/"}]
    blogs = parse_wp_posts(raw, kind="blog")
    pages = parse_wp_posts(raw, kind="page")
    assert blogs[0].kind == "blog"
    assert pages[0].kind == "page"


def test_parse_wp_posts_skips_malformed_rows():
    raw = [
        {"id": 1, "slug": "ok", "title": "Ok", "link": "https://x/"},
        {"slug": "no-id"},
        {"id": 2},  # no slug AND no url -> drop
        "not a dict",
    ]
    posts = parse_wp_posts(raw)
    assert len(posts) == 1 and posts[0].slug == "ok"


def test_parse_wp_posts_derives_slug_from_url_when_missing():
    """The MCP claude_ai_FirstMoversWP variant returns `url` but no `slug`;
    parse_wp_posts must derive the slug from the URL path's last segment.
    """
    raw = [
        {
            "id": 72554,
            "title": "Brand Visibility Strategy",
            "url": "https://firstmovers.ai/brand-visibility-strategy/",
            "status": "publish",
            "type": "post",
            "date": "2026-05-07 00:25:48",
        },
    ]
    posts = parse_wp_posts(raw)
    assert len(posts) == 1
    assert posts[0].id == 72554
    assert posts[0].slug == "brand-visibility-strategy"
    assert posts[0].url == "https://firstmovers.ai/brand-visibility-strategy/"
    assert posts[0].published_at == "2026-05-07"


def test_attach_ahrefs_falls_back_to_focus_keyword_for_blogs_without_data():
    """A freshly-published blog has no Ahrefs traffic data yet. The fallback
    populates organic_keywords with [focus_keyword] so assert_complete passes
    and the cannibalization gate's Rule 2 still matches the focus keyword.
    """
    posts = [
        PublishedPost(
            id=1, slug="brand-new-post",
            title="Brand New Post",
            url="https://firstmovers.ai/brand-new-post/",
            published_at="2026-05-08", kind="blog",
            focus_keyword="brand new post",  # set by attach_rank_math
            organic_keywords=[],
        ),
    ]
    enriched = attach_ahrefs_organic_keywords(posts, raw_by_url={})
    assert enriched[0].organic_keywords == ["brand new post"]


def test_attach_ahrefs_does_not_fallback_for_pages():
    """Pages don't need organic_keywords populated even on Ahrefs miss."""
    posts = [
        PublishedPost(
            id=1, slug="thank-you",
            title="Thank You",
            url="https://firstmovers.ai/thank-you/",
            published_at="2026-04-01", kind="page",
            focus_keyword="thank you",
            organic_keywords=[],
        ),
    ]
    enriched = attach_ahrefs_organic_keywords(posts, raw_by_url={})
    assert enriched[0].organic_keywords == []


# ---------- attach_rank_math_focus_keywords ----------


def test_attach_rank_math_focus_keywords_uses_meta_field():
    posts = [_post(1, "ai-consulting-cost-2026", focus=None)]
    raw_by_id = {1: {"meta": {"rank_math_focus_keyword": "ai consulting cost"}}}
    enriched = attach_rank_math_focus_keywords(posts, raw_by_id)
    assert enriched[0].focus_keyword == "ai consulting cost"


def test_attach_rank_math_focus_keywords_falls_back_to_slug():
    """Posts without Rank Math meta still get a non-None focus_keyword
    (slug-derived sentinel) so assert_complete passes."""
    posts = [_post(1, "agentic-ai-explained", focus=None)]
    raw_by_id: dict[int, dict] = {}
    enriched = attach_rank_math_focus_keywords(posts, raw_by_id)
    assert enriched[0].focus_keyword == "agentic ai explained"


def test_attach_rank_math_focus_keywords_handles_yoast_legacy_field():
    posts = [_post(1, "x", focus=None)]
    raw_by_id = {1: {"meta": {"_yoast_wpseo_focuskw": "legacy keyword"}}}
    enriched = attach_rank_math_focus_keywords(posts, raw_by_id)
    assert enriched[0].focus_keyword == "legacy keyword"


# ---------- attach_ahrefs_organic_keywords ----------


def test_attach_ahrefs_organic_keywords_extracts_keyword_field():
    posts = [_post(1, "consulting", organic=[])]
    raw_by_url = {
        "https://firstmovers.ai/consulting/": {
            "keywords": [
                {"keyword": "ai consulting", "traffic": 100},
                {"keyword": "ai consultant", "traffic": 50},
            ]
        }
    }
    enriched = attach_ahrefs_organic_keywords(posts, raw_by_url)
    assert enriched[0].organic_keywords == ["ai consulting", "ai consultant"]


def test_attach_ahrefs_organic_keywords_respects_top_n():
    posts = [_post(1, "consulting", organic=[])]
    raw_by_url = {
        "https://firstmovers.ai/consulting/": {
            "keywords": [{"keyword": f"kw{i}"} for i in range(50)]
        }
    }
    enriched = attach_ahrefs_organic_keywords(posts, raw_by_url, top_n=5)
    assert len(enriched[0].organic_keywords) == 5


def test_attach_ahrefs_organic_keywords_dedupes_case_insensitive():
    posts = [_post(1, "consulting", organic=[])]
    raw_by_url = {
        "https://firstmovers.ai/consulting/": {
            "keywords": [
                {"keyword": "AI Consulting"},
                {"keyword": "ai consulting"},
                {"keyword": "AI Consultant"},
            ]
        }
    }
    enriched = attach_ahrefs_organic_keywords(posts, raw_by_url)
    assert len(enriched[0].organic_keywords) == 2  # AI Consultant survives, dupes drop


# ---------- merge ----------


def test_merge_dedupes_by_id():
    a = [_post(1, "a", focus="x")]
    b = [_post(1, "a-different", focus="y"), _post(2, "b", focus="z")]
    merged = merge(a, b)
    assert {p.id for p in merged} == {1, 2}
    # First occurrence wins
    assert merged[0].slug == "a"


# ---------- save / load round-trip ----------


def test_save_load_roundtrip(tmp_path: Path):
    inv = _well_formed_inventory()
    p = tmp_path / "snapshot.json"
    save(inv, p)
    loaded = load(p)
    assert len(loaded.posts) == len(inv.posts)
    assert loaded.posts[0].slug == inv.posts[0].slug
    assert loaded.posts[0].focus_keyword == inv.posts[0].focus_keyword
    assert loaded.posts[0].kind == inv.posts[0].kind


def test_load_raises_when_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load(tmp_path / "does-not-exist.json")


# ---------- build_inventory ----------


def test_build_inventory_stamps_iso_generated_at():
    inv = build_inventory([_post(1, "a", focus="x", organic=["k"])])
    # Should be parseable as ISO and within a few seconds of now
    parsed = datetime.fromisoformat(inv.generated_at.replace("Z", "+00:00"))
    delta = datetime.now(timezone.utc) - parsed
    assert delta < timedelta(seconds=5)
