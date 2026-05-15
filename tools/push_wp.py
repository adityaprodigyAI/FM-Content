"""push_wp — push drafts to WordPress with WAF fallback.

The Cloudways/Wordfence WAF blocks WordPress writes from cloud-agent IP
ranges. v5 of the pipeline hit this on W21. The fix is "Path B": queue
the draft to disk and trigger a GitHub Actions workflow that runs from a
non-cloud IP.

This module decides between MCP push (preferred) and Path B fallback. The
agent makes the actual MCP call; this module produces the payload, parses
the response, and queues to disk on failure.

Two operating modes:
  - **From a Claude session:** call `build_create_payload(...)` to get the
    `wp_add_post` MCP payload. Make the MCP call. Pass the response to
    `parse_create_response(...)`. On success, you have the post ID. On
    WAF block (403), call `queue_for_path_b(...)` and trigger the GH
    Actions workflow.
  - **From the GH Actions runner:** call `push_via_app_password(...)`
    directly with HTTP basic auth. This bypasses the MCP entirely.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .identities import (
    JOSH_MCCOY_WP_USER_ID,
    SITE_BASE_URL,
    SITE_HOST,
    VALID_WP_CATEGORY_IDS,
)

PENDING_PUSH_DIR: Final[Path] = (
    Path(__file__).resolve().parents[1] / "data" / "runs" / "_pending-push"
)

WP_REST_POSTS_ENDPOINT: Final[str] = "/wp-json/wp/v2/posts"


# ---------------------------------------------------------------------------
# Domain check — never push to anything but firstmovers.ai
# ---------------------------------------------------------------------------


def _ensure_firstmovers_host(url: str) -> None:
    """Refuse to push to any host other than firstmovers.ai.

    The v5 pipeline had a single source-of-truth for this; we keep it.
    """
    if SITE_HOST not in url:
        raise ValueError(
            f"refusing to push to {url!r}: only {SITE_HOST} is permitted"
        )


# ---------------------------------------------------------------------------
# MCP payload builder + response parser
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreatePostPayload:
    """The `wp_add_post` MCP payload."""

    title: str
    content: str
    slug: str
    excerpt: str
    status: str
    categories: list[int]
    author: int | None  # None means "let WordPress assign the API user"


def build_create_payload(
    *,
    title: str,
    content: str,
    slug: str,
    excerpt: str,
    category_id: int,
    author: int | None = JOSH_MCCOY_WP_USER_ID,
) -> CreatePostPayload:
    if category_id not in VALID_WP_CATEGORY_IDS:
        raise ValueError(
            f"category_id {category_id} not valid; must be one of "
            f"{sorted(VALID_WP_CATEGORY_IDS)}"
        )
    import re
    if not slug or not re.match(r"^[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?$", slug):
        raise ValueError(f"slug {slug!r} must be lowercase a-z, 0-9, hyphens")
    return CreatePostPayload(
        title=title,
        content=content,
        slug=slug,
        excerpt=excerpt,
        status="draft",  # NEVER publish — Nikki is the only publish gate
        categories=[category_id],
        author=author,
    )


def parse_create_response(raw: Any) -> dict[str, Any] | None:
    """Pull the post id + edit URL from a wp_add_post response.

    Returns None on parse failure or non-success.
    """
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("type") == "text":
        try:
            raw = json.loads(raw[0].get("text", "null"))
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(raw, dict):
        return None
    pid = raw.get("id") or raw.get("ID") or raw.get("post_id")
    if not pid:
        return None
    edit_url = raw.get("edit_url") or _build_edit_url(int(pid))
    preview_url = raw.get("preview_url") or _build_preview_url(int(pid))
    return {
        "id": int(pid),
        "edit_url": edit_url,
        "preview_url": preview_url,
        "slug": raw.get("slug"),
        "link": raw.get("link") or raw.get("url"),
        "status": raw.get("status"),
    }


def is_waf_block(error: Exception | dict | int) -> bool:
    """Detect Cloudways/Wordfence block patterns.

    Accepts a raised exception, an error dict from the MCP, or a status code.
    """
    if isinstance(error, int):
        return error == 403
    if isinstance(error, dict):
        msg = json.dumps(error).lower()
        return any(s in msg for s in ("403", "forbidden", "wordfence", "cloudflare"))
    if isinstance(error, Exception):
        msg = str(error).lower()
        return any(s in msg for s in ("403", "forbidden", "wordfence", "cloudflare"))
    return False


# ---------------------------------------------------------------------------
# Path B — queue to disk, GH Actions picks it up
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingPush:
    payload: CreatePostPayload
    rank_math_meta: dict[str, str]
    week: str


def queue_for_path_b(
    pending: PendingPush,
    *,
    dir_: Path = PENDING_PUSH_DIR,
) -> Path:
    """Write the pending push to disk so the GH Actions workflow can find it."""
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"{pending.payload.slug}.json"
    payload = {
        "post": {
            "title": pending.payload.title,
            "content": pending.payload.content,
            "slug": pending.payload.slug,
            "excerpt": pending.payload.excerpt,
            "status": pending.payload.status,
            "categories": pending.payload.categories,
            "author": pending.payload.author,
        },
        "rank_math_meta": pending.rank_math_meta,
        "week": pending.week,
        "wp_post_id": None,  # populated by the GH Actions runner after push
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def list_pending_pushes(dir_: Path = PENDING_PUSH_DIR) -> list[Path]:
    if not dir_.exists():
        return []
    return sorted(p for p in dir_.glob("*.json") if p.is_file())


# ---------------------------------------------------------------------------
# Path B — direct WP REST push from GH Actions runner
# ---------------------------------------------------------------------------


def push_via_app_password(
    payload_json: dict[str, Any],
    *,
    user: str,
    app_password: str,
    site_base_url: str = SITE_BASE_URL,
    timeout: int = 30,
) -> dict[str, Any]:
    """POST `/wp-json/wp/v2/posts` with HTTP basic auth.

    `payload_json` is the dict written to data/runs/_pending-push/<slug>.json.
    Returns the parsed WP REST response on success.

    Used from the GitHub Actions runner where the WAF rule doesn't apply.
    """
    _ensure_firstmovers_host(site_base_url)
    post = payload_json.get("post") or {}
    if post.get("status") != "draft":
        raise ValueError("refusing to push: post.status is not 'draft'")

    body = {
        "title": post.get("title", ""),
        "content": post.get("content", ""),
        "slug": post.get("slug", ""),
        "excerpt": post.get("excerpt", ""),
        "status": "draft",
        "categories": post.get("categories", []),
    }
    author = post.get("author")
    if author is not None:
        body["author"] = int(author)

    url = site_base_url.rstrip("/") + WP_REST_POSTS_ENDPOINT
    data = json.dumps(body).encode("utf-8")
    auth = _basic_auth(user, app_password)
    req = Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": auth,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — known host
            text = resp.read().decode("utf-8")
            return json.loads(text)
    except HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            f"WP REST POST failed: HTTP {e.code} {e.reason}; body: {body_text[:500]}"
        ) from e


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_edit_url(post_id: int) -> str:
    return f"{SITE_BASE_URL}/wp-admin/post.php?post={post_id}&action=edit"


def _build_preview_url(post_id: int) -> str:
    return f"{SITE_BASE_URL}/?p={post_id}&preview=true"


def _basic_auth(user: str, password: str) -> str:
    import base64
    pair = f"{user}:{password}".encode("utf-8")
    return "Basic " + base64.b64encode(pair).decode("ascii")
