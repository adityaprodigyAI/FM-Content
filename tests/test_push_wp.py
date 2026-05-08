"""Tests for tools/push_wp.py.

Covers payload building, response parsing, WAF detection, and Path B
(disk-queue) shape. No network calls.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.push_wp import (
    CreatePostPayload,
    PendingPush,
    build_create_payload,
    is_waf_block,
    list_pending_pushes,
    parse_create_response,
    queue_for_path_b,
)


# ---------- build_create_payload ----------


def test_build_create_payload_forces_status_draft():
    p = build_create_payload(
        title="X", content="<p>x</p>", slug="some-slug",
        excerpt="excerpt", category_id=27,
    )
    assert p.status == "draft"
    assert p.categories == [27]


def test_build_create_payload_rejects_invalid_category():
    with pytest.raises(ValueError, match="category_id"):
        build_create_payload(
            title="X", content="<p>x</p>", slug="x",
            excerpt="x", category_id=999,
        )


def test_build_create_payload_rejects_invalid_slug():
    with pytest.raises(ValueError, match="slug"):
        build_create_payload(
            title="X", content="<p>x</p>", slug="UPPERCASE",
            excerpt="x", category_id=27,
        )


def test_build_create_payload_allows_optional_author_override():
    p = build_create_payload(
        title="X", content="<p>x</p>", slug="x",
        excerpt="x", category_id=27, author=None,
    )
    assert p.author is None


# ---------- parse_create_response ----------


def test_parse_create_response_pulls_id():
    resp = {"id": 12345, "slug": "x", "link": "https://firstmovers.ai/x/", "status": "draft"}
    parsed = parse_create_response(resp)
    assert parsed is not None
    assert parsed["id"] == 12345
    assert "wp-admin" in parsed["edit_url"]
    assert "preview=true" in parsed["preview_url"]


def test_parse_create_response_handles_mcp_text_wrapper():
    resp = [{"type": "text", "text": json.dumps({"id": 999, "slug": "y", "status": "draft"})}]
    parsed = parse_create_response(resp)
    assert parsed and parsed["id"] == 999


def test_parse_create_response_returns_none_on_failure():
    assert parse_create_response(None) is None
    assert parse_create_response("not json") is None
    assert parse_create_response({"no_id_field": True}) is None


# ---------- is_waf_block ----------


def test_is_waf_block_detects_403():
    assert is_waf_block(403)


def test_is_waf_block_detects_wordfence_in_message():
    assert is_waf_block(Exception("Wordfence blocked the request"))


def test_is_waf_block_detects_forbidden_in_dict():
    assert is_waf_block({"error": "403 forbidden by firewall"})


def test_is_waf_block_returns_false_on_normal_error():
    assert not is_waf_block(Exception("Connection timeout"))
    assert not is_waf_block(500)


# ---------- queue_for_path_b ----------


def test_queue_for_path_b_writes_well_formed_json(tmp_path: Path):
    payload = build_create_payload(
        title="Test Title", content="<p>body</p>", slug="test-slug",
        excerpt="excerpt", category_id=27,
    )
    pending = PendingPush(
        payload=payload,
        rank_math_meta={
            "rank_math_focus_keyword": "test focus",
            "rank_math_title": "Test SEO Title",
            "rank_math_description": "Test meta description",
        },
        week="2026-W22",
    )
    written = queue_for_path_b(pending, dir_=tmp_path)
    assert written.exists()
    data = json.loads(written.read_text())
    assert data["post"]["status"] == "draft"
    assert data["post"]["categories"] == [27]
    assert data["post"]["slug"] == "test-slug"
    assert data["rank_math_meta"]["rank_math_focus_keyword"] == "test focus"
    assert data["wp_post_id"] is None
    assert data["week"] == "2026-W22"


def test_list_pending_pushes_returns_sorted_files(tmp_path: Path):
    (tmp_path / "b.json").write_text("{}")
    (tmp_path / "a.json").write_text("{}")
    (tmp_path / "c.txt").write_text("not json")  # should be ignored
    pending = list_pending_pushes(tmp_path)
    names = [p.name for p in pending]
    assert names == ["a.json", "b.json"]


def test_list_pending_pushes_returns_empty_when_dir_missing(tmp_path: Path):
    assert list_pending_pushes(tmp_path / "nope") == []
