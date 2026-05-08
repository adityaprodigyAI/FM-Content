"""Tests for tools/rank_math.py."""

from __future__ import annotations

from tools.rank_math import (
    RANK_MATH_ENDPOINT_PATH,
    build_meta,
    endpoint_url,
    to_payload,
)


def test_build_meta_constructs_canonical_url():
    meta = build_meta(
        focus_keyword="ai inbox automation",
        seo_title="AI Inbox Automation: Proven 2026 Guide",
        meta_description="...",
        slug="ai-inbox-automation-2026",
    )
    assert meta.canonical_url == "https://firstmovers.ai/ai-inbox-automation-2026/"


def test_to_payload_uses_devora_field_names():
    meta = build_meta(
        focus_keyword="x",
        seo_title="Y",
        meta_description="z",
        slug="s",
    )
    payload = to_payload(123, meta)
    assert payload["objectID"] == 123
    assert payload["objectType"] == "post"
    assert payload["meta"]["rank_math_focus_keyword"] == "x"
    assert payload["meta"]["rank_math_title"] == "Y"
    assert payload["meta"]["rank_math_description"] == "z"
    assert payload["meta"]["rank_math_canonical_url"].endswith("/s/")


def test_endpoint_url_uses_constant():
    url = endpoint_url("https://firstmovers.ai")
    assert url.endswith(RANK_MATH_ENDPOINT_PATH)
