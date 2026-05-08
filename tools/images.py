"""images — Pexels search + hotlinked image references.

Cloudways/Wordfence WAF blocks `wp_upload_media` and direct REST POSTs to
`/wp/v2/media` from cloud agents. So we hotlink Pexels CDN URLs into the
post body. Rank Math grades hotlinked `<img>` tags identically to library-
hosted ones; we lose only the WP-managed featured-image thumbnail.

Pexels attribution is required by their API license. Every `<figcaption>`
shows `Photo by <Photographer> on Pexels` with `rel="nofollow noopener"`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Final
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PEXELS_API_KEY_ENV_VAR: Final[str] = "PEXELS_API_KEY"
PEXELS_SEARCH_ENDPOINT: Final[str] = "https://api.pexels.com/v1/search"


@dataclass(frozen=True)
class ImageRef:
    """A Pexels image with everything needed to render a `<figure>` block."""

    url: str             # CDN URL (large or large2x)
    alt: str             # alt text — pass focus_keyword in for the hero
    photographer: str
    photographer_url: str
    pexels_url: str      # Pexels page URL for attribution
    width: int
    height: int


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_pexels(
    focus_keyword: str,
    *,
    count: int = 4,
    api_key: str | None = None,
    orientation: str = "landscape",
) -> list[ImageRef]:
    """Fetch `count` Pexels images matching `focus_keyword`.

    Network call. The agent should normally pre-fetch and pass `raw_response`
    to `parse_pexels_response` instead — this convenience helper exists for
    interactive testing.

    Set PEXELS_API_KEY env var or pass `api_key`.
    """
    key = api_key or os.environ.get(PEXELS_API_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"PEXELS_API_KEY not set. Set the env var or pass api_key=."
        )
    qs = urlencode({"query": focus_keyword, "per_page": count, "orientation": orientation})
    req = Request(
        f"{PEXELS_SEARCH_ENDPOINT}?{qs}",
        headers={"Authorization": key},
    )
    with urlopen(req, timeout=15) as resp:  # noqa: S310 — known-safe URL
        body = resp.read().decode("utf-8")
    return parse_pexels_response(json.loads(body), focus_keyword=focus_keyword)


def parse_pexels_response(raw: Any, *, focus_keyword: str) -> list[ImageRef]:
    """Parse a Pexels search response (or wrapped MCP shape) into ImageRefs.

    Expects:
      {"photos": [{"src": {"large": "..."}, "photographer": "...",
                   "photographer_url": "...", "url": "...",
                   "width": 1200, "height": 800, "alt": "..."}, ...]}
    """
    if isinstance(raw, list) and raw and isinstance(raw[0], dict) and raw[0].get("type") == "text":
        try:
            raw = json.loads(raw[0].get("text", "null"))
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw, dict):
        return []
    photos = raw.get("photos") or []
    if not isinstance(photos, list):
        return []

    out: list[ImageRef] = []
    for photo in photos:
        if not isinstance(photo, dict):
            continue
        src = photo.get("src") or {}
        if not isinstance(src, dict):
            continue
        url = src.get("large2x") or src.get("large") or src.get("original")
        if not url:
            continue
        out.append(
            ImageRef(
                url=str(url),
                alt=photo.get("alt") or focus_keyword,
                photographer=str(photo.get("photographer") or "Pexels Contributor"),
                photographer_url=str(photo.get("photographer_url") or "https://www.pexels.com"),
                pexels_url=str(photo.get("url") or "https://www.pexels.com"),
                width=int(photo.get("width") or 0),
                height=int(photo.get("height") or 0),
            )
        )
    return out


def render_figure(image: ImageRef, *, alt_override: str | None = None,
                  is_hero: bool = False) -> str:
    """Render a `<figure>` block with image, alt, and Pexels attribution caption."""
    alt = alt_override or image.alt
    classes = "fm-image" + (" fm-image-hero" if is_hero else "")
    return (
        f'<figure class="{classes}">\n'
        f'  <img src="{image.url}" alt="{_escape(alt)}" '
        f'loading="lazy" width="{image.width}" height="{image.height}">\n'
        f'  <figcaption>'
        f'Photo by <a href="{image.photographer_url}" '
        f'rel="nofollow noopener" target="_blank">{_escape(image.photographer)}</a> '
        f'on <a href="{image.pexels_url}" rel="nofollow noopener" '
        f'target="_blank">Pexels</a>'
        f'</figcaption>\n'
        f'</figure>'
    )


def hero_alt(focus_keyword: str, first_h2_text: str) -> str:
    """Compose hero image alt text. Guarantees focus keyword presence
    (`rubric._validate_images`)."""
    h2 = (first_h2_text or "").strip()
    if h2 and focus_keyword.lower() not in h2.lower():
        return f"{focus_keyword}: {h2}"
    return focus_keyword


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
