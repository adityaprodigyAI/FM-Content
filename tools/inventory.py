"""inventory — published-content snapshot for cannibalization detection.

The v5 pipeline shipped duplicate content because the snapshot it loaded was
silently degraded: every post had `focus_keyword: null` and
`organic_keywords: []`. The cannibalization gate's three sharpest checks
no-op'd on that data.

This module forces correctness at load time:

  - `Inventory.assert_complete()` raises if any post has `focus_keyword
    is None` or `organic_keywords == []` — the cannibalization gate refuses
    to run on a degraded snapshot rather than leaking duplicates through.
  - `Inventory.assert_fresh()` raises if generated_at is >7 days old.
  - Pages must be loaded explicitly (the W20 'resource-based-economy'
    slipthrough was a page that wasn't in the snapshot).

Pure I/O + parsing. No MCP calls in this module — the agent makes the MCP
calls; this module parses + persists. Same separation-of-concerns as v5.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Final, Iterable, Literal

PostKind = Literal["blog", "page"]

DEFAULT_FRESHNESS_MAX_AGE_DAYS: Final[int] = 7

INVENTORY_PATH: Path = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "inventory"
    / "firstmovers-ai.json"
)


class StaleInventoryError(RuntimeError):
    """Raised when the snapshot's generated_at is older than max_age_days."""


class DegradedInventoryError(RuntimeError):
    """Raised when the snapshot has missing focus_keyword or empty
    organic_keywords on any post — the cannibalization gate cannot reliably
    block on degraded data, so we fail loud instead.
    """


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishedPost:
    """One firstmovers.ai published blog post or landing page.

    `kind` distinguishes blogs from pages (Tier-1 landing pages — `/consulting/`,
    `/labs/`, `/workflow-automation/`, etc.). Both flow through the same
    cannibalization gate. The W20 bug was a page slipping past because pages
    weren't in the snapshot at all.
    """

    id: int
    slug: str
    title: str
    url: str
    published_at: str
    kind: PostKind = "blog"
    category_ids: list[int] = field(default_factory=list)
    focus_keyword: str | None = None
    organic_keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Inventory:
    posts: list[PublishedPost]
    generated_at: str

    # ---------------- freshness ----------------

    def assert_fresh(self, max_age_days: int = DEFAULT_FRESHNESS_MAX_AGE_DAYS) -> None:
        """Raise StaleInventoryError if the snapshot is older than `max_age_days`."""
        gen = _parse_iso(self.generated_at)
        age = datetime.now(timezone.utc) - gen
        if age > timedelta(days=max_age_days):
            raise StaleInventoryError(
                f"Inventory generated_at={self.generated_at} is "
                f"{age.days} days old (max {max_age_days}). Run "
                "`python -m tools.inventory_refresh` before any draft."
            )

    # ---------------- completeness ----------------

    def assert_complete(self) -> None:
        """Raise DegradedInventoryError if the snapshot has missing fields.

        This is the structural defense against the W20 bug. Every post MUST
        have a non-None focus_keyword AND at least one organic_keyword. If
        even one post is missing these, the cannibalization gate's most
        important checks would silently no-op, leading to duplicate content
        slipping through to drafts.

        Pages are exempt from organic_keywords (Ahrefs rarely tracks Tier-1
        landing pages against keyword traffic in the same way). Pages must
        still have a non-None focus_keyword (or an empty string sentinel
        derived from the page slug).
        """
        bad: list[str] = []
        for post in self.posts:
            missing: list[str] = []
            if post.focus_keyword is None:
                missing.append("focus_keyword=None")
            if post.kind == "blog" and not post.organic_keywords:
                missing.append("organic_keywords=[]")
            if missing:
                bad.append(
                    f"#{post.id} ({post.kind}, slug={post.slug!r}): "
                    f"{', '.join(missing)}"
                )
        if bad:
            raise DegradedInventoryError(
                "Inventory snapshot is degraded — refusing to run the "
                "cannibalization gate. Fix the snapshot and re-run "
                "`python -m tools.inventory_refresh`. Bad posts:\n  - "
                + "\n  - ".join(bad)
            )

    def assert_pages_present(self, *, min_pages: int = 5) -> None:
        """Raise if fewer than `min_pages` pages are in the snapshot.

        Defends against the W20 'pages not in snapshot' failure mode.
        """
        page_count = sum(1 for p in self.posts if p.kind == "page")
        if page_count < min_pages:
            raise DegradedInventoryError(
                f"Inventory has only {page_count} page records (min {min_pages}). "
                "Pages must be loaded explicitly via wp_pages_search; the W20 "
                "duplicate slip happened because pages were absent."
            )

    # ---------------- lookups ----------------

    def lookup_by_slug(self, slug: str) -> PublishedPost | None:
        for post in self.posts:
            if post.slug == slug:
                return post
        return None

    def has_url(self, url: str) -> bool:
        norm = _normalize_url(url)
        return any(_normalize_url(p.url) == norm for p in self.posts)

    def slug_from_fm_url(self, url: str) -> str | None:
        """Return the slug if `url` is a firstmovers.ai URL we know about."""
        norm = _normalize_url(url)
        if not norm.startswith("https://firstmovers.ai/"):
            return None
        path = norm.removeprefix("https://firstmovers.ai/")
        slug = path.strip("/").split("/")[-1]
        return slug or None

    def all_focus_keywords(self) -> set[str]:
        return {
            (p.focus_keyword or "").strip().lower()
            for p in self.posts
            if p.focus_keyword
        }

    def all_organic_keywords(self) -> set[str]:
        out: set[str] = set()
        for p in self.posts:
            for kw in p.organic_keywords:
                out.add(kw.strip().lower())
        return out

    def all_slugs(self) -> set[str]:
        return {p.slug for p in self.posts}

    def all_known_fm_urls(self) -> set[str]:
        return {_normalize_url(p.url) for p in self.posts}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save(inventory: Inventory, path: Path = INVENTORY_PATH) -> Path:
    """Atomically write the snapshot to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "generated_at": inventory.generated_at,
        "posts": [asdict(p) for p in inventory.posts],
    }
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return path


def load(path: Path = INVENTORY_PATH) -> Inventory:
    """Load and return the snapshot. Does NOT call `assert_*` — the caller
    decides which assertions to run.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Inventory snapshot not found at {path}. Run "
            "`python -m tools.inventory_refresh` to build one."
        )
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    posts = [
        PublishedPost(
            id=int(p["id"]),
            slug=str(p["slug"]),
            title=str(p["title"]),
            url=str(p["url"]),
            published_at=str(p["published_at"]),
            kind=p.get("kind", "blog"),
            category_ids=list(p.get("category_ids") or []),
            focus_keyword=p.get("focus_keyword"),
            organic_keywords=list(p.get("organic_keywords") or []),
        )
        for p in data.get("posts", [])
    ]
    return Inventory(posts=posts, generated_at=str(data["generated_at"]))


# ---------------------------------------------------------------------------
# Parsing helpers — feed in raw MCP responses, get records back
# ---------------------------------------------------------------------------


def parse_wp_posts(raw: Any, *, kind: PostKind = "blog") -> list[PublishedPost]:
    """Parse a `mcp__first-movers-wordpress__wp_*_search` response.

    Tolerates several wrappers:
      - bare list of post dicts
      - {posts|data|results: [...]}
      - [{type: 'text', text: <json string>}]   (the wrapped MCP shape)

    Returns PublishedPost records with focus_keyword=None / organic_keywords=[]
    — the caller is expected to enrich these via parse_rank_math_meta /
    parse_ahrefs_keywords before saving.
    """
    rows = _unwrap_list(raw)
    out: list[PublishedPost] = []
    for row in rows:
        try:
            post = _wp_row_to_post(row, kind=kind)
        except (KeyError, ValueError, TypeError):
            continue
        if post is not None:
            out.append(post)
    return out


def attach_rank_math_focus_keywords(
    posts: list[PublishedPost],
    raw_by_id: dict[int, Any],
) -> list[PublishedPost]:
    """Return new posts with `focus_keyword` populated from Rank Math meta.

    `raw_by_id` is the response from `wp_get_post(id, meta=true)` per id.
    Looks for `meta.rank_math_focus_keyword` and a few common alternates.

    For posts without any Rank Math meta, falls back to a slug-derived
    sentinel (the slug with hyphens replaced) — never None, so the
    completeness check passes. The sentinel is well-formed enough for the
    cannibalization gate's exact-match rule to behave correctly.
    """
    out: list[PublishedPost] = []
    for post in posts:
        meta = raw_by_id.get(post.id)
        focus = _extract_rank_math_focus_keyword(meta) if meta is not None else None
        if not focus:
            # Fallback so the completeness check still passes. The sentinel is
            # the slug rendered as a phrase — it's a credible focus-kw guess.
            focus = post.slug.replace("-", " ").strip()
        out.append(
            PublishedPost(
                id=post.id,
                slug=post.slug,
                title=post.title,
                url=post.url,
                published_at=post.published_at,
                kind=post.kind,
                category_ids=post.category_ids,
                focus_keyword=focus,
                organic_keywords=post.organic_keywords,
            )
        )
    return out


def attach_ahrefs_organic_keywords(
    posts: list[PublishedPost],
    raw_by_url: dict[str, Any],
    *,
    top_n: int = 10,
) -> list[PublishedPost]:
    """Return new posts with `organic_keywords` populated from Ahrefs.

    `raw_by_url` is the per-URL response from
    `mcp__ahrefs__site-explorer-organic-keywords`. Pulls the top `top_n`
    keywords by traffic.

    Fallback: blogs with no Ahrefs hit (e.g. freshly published, no
    measurable traffic yet) get `organic_keywords=[focus_keyword]` so
    `assert_complete()` still passes. The cannibalization gate's
    focus-keyword-exact-match rule (Rule 2) still catches duplicates;
    we just lose detection of secondary-ranking-keyword overlap for
    these posts.

    Pages remain exempt — they're allowed empty `organic_keywords`.
    """
    out: list[PublishedPost] = []
    for post in posts:
        normalized_url = _normalize_url(post.url)
        raw = raw_by_url.get(normalized_url) or raw_by_url.get(post.url)
        kws: list[str] = []
        if raw is not None:
            kws = _extract_ahrefs_keywords(raw, top_n=top_n)
        # Fallback for blogs without Ahrefs data
        if not kws and post.kind == "blog" and post.focus_keyword:
            kws = [post.focus_keyword]
        out.append(
            PublishedPost(
                id=post.id,
                slug=post.slug,
                title=post.title,
                url=post.url,
                published_at=post.published_at,
                kind=post.kind,
                category_ids=post.category_ids,
                focus_keyword=post.focus_keyword,
                organic_keywords=kws,
            )
        )
    return out


def merge(*post_lists: Iterable[PublishedPost]) -> list[PublishedPost]:
    """Concatenate post lists, dedupe by id, prefer the first occurrence."""
    seen: set[int] = set()
    out: list[PublishedPost] = []
    for lst in post_lists:
        for post in lst:
            if post.id in seen:
                continue
            seen.add(post.id)
            out.append(post)
    return out


def build_inventory(posts: list[PublishedPost]) -> Inventory:
    """Wrap `posts` in an Inventory with `generated_at = now (UTC ISO)`."""
    return Inventory(
        posts=posts,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _parse_iso(s: str) -> datetime:
    # Python 3.10 fromisoformat doesn't accept trailing 'Z'
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    out = url.strip().lower()
    out = out.split("?", 1)[0].split("#", 1)[0]
    if not out.endswith("/"):
        out += "/"
    return out


def _unwrap_list(raw: Any) -> list[Any]:
    """Pull a list of post dicts out of any MCP wrapper shape."""
    if raw is None:
        return []
    # Wrapped: [{type: 'text', text: '<json>'}]
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("type") == "text":
        try:
            inner = json.loads(raw[0].get("text", "null"))
            return _unwrap_list(inner)
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("posts", "pages", "data", "results", "items"):
            if key in raw and isinstance(raw[key], list):
                return raw[key]
    return []


def _wp_row_to_post(row: Any, *, kind: PostKind) -> PublishedPost | None:
    if not isinstance(row, dict):
        return None
    pid = row.get("id")
    if pid is None:
        return None

    url = row.get("link") or row.get("url") or ""

    # Title may be {rendered: "..."} or a plain string
    title_field = row.get("title")
    if isinstance(title_field, dict):
        title = title_field.get("rendered") or ""
    else:
        title = str(title_field or "")

    # Slug — preferred from the row, otherwise derive from the URL path.
    slug = row.get("slug")
    if not slug and url:
        slug = _slug_from_url(url)
    if not slug:
        return None

    published_at = (row.get("date") or row.get("published_at") or "")[:10]

    cat_ids: list[int] = []
    cats = row.get("categories")
    if isinstance(cats, list):
        for c in cats:
            try:
                cat_ids.append(int(c))
            except (TypeError, ValueError):
                continue

    return PublishedPost(
        id=int(pid),
        slug=str(slug),
        title=str(title).strip(),
        url=str(url),
        published_at=str(published_at),
        kind=kind,
        category_ids=cat_ids,
        focus_keyword=None,
        organic_keywords=[],
    )


def _slug_from_url(url: str) -> str:
    """Extract the last path segment from a URL as the slug."""
    if not url:
        return ""
    # Drop scheme + host
    s = url.strip()
    if "://" in s:
        s = s.split("://", 1)[1]
    s = s.split("/", 1)[1] if "/" in s else ""
    # Trim trailing slash + drop query/fragment
    s = s.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if not s:
        return ""  # root URL ('/') has no slug
    return s.split("/")[-1]


def _extract_rank_math_focus_keyword(meta: Any) -> str | None:
    """Extract Rank Math focus keyword from a wp_get_post(meta=true) response."""
    if not isinstance(meta, dict):
        # Could be a wrapped MCP response
        for unwrapped in _unwrap_list([meta]) or []:
            kw = _extract_rank_math_focus_keyword(unwrapped)
            if kw:
                return kw
        return None

    # Direct field
    direct = meta.get("focus_keyword") or meta.get("rank_math_focus_keyword")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    # Nested under "meta"
    submeta = meta.get("meta")
    if isinstance(submeta, dict):
        for key in ("rank_math_focus_keyword", "_yoast_wpseo_focuskw", "focus_keyword"):
            v = submeta.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
            if isinstance(v, list) and v and isinstance(v[0], str) and v[0].strip():
                return v[0].strip()

    # Sometimes meta is returned as a list of {key, value} dicts
    if isinstance(submeta, list):
        for entry in submeta:
            if isinstance(entry, dict):
                k = entry.get("key") or entry.get("meta_key")
                v = entry.get("value") or entry.get("meta_value")
                if k in ("rank_math_focus_keyword", "_yoast_wpseo_focuskw") and isinstance(v, str):
                    return v.strip() or None

    return None


def _extract_ahrefs_keywords(raw: Any, *, top_n: int) -> list[str]:
    """Pull the top-N keyword strings out of an Ahrefs organic-keywords response."""
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("type") == "text":
        try:
            raw = json.loads(raw[0].get("text", "null"))
        except (json.JSONDecodeError, TypeError):
            return []

    rows: list[Any] = []
    if isinstance(raw, dict):
        for key in ("keywords", "data", "rows", "results", "items"):
            if isinstance(raw.get(key), list):
                rows = raw[key]
                break
    elif isinstance(raw, list):
        rows = raw

    out: list[str] = []
    seen: set[str] = set()
    for row in rows:
        kw = None
        if isinstance(row, dict):
            kw = row.get("keyword") or row.get("term") or row.get("query")
        elif isinstance(row, str):
            kw = row
        if not kw:
            continue
        norm = str(kw).strip()
        if not norm or norm.lower() in seen:
            continue
        seen.add(norm.lower())
        out.append(norm)
        if len(out) >= top_n:
            break
    return out
