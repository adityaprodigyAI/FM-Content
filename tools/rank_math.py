"""rank_math — set focus_keyword / seo_title / meta_description / canonical_url.

Without the Devora-AS/rank-math-api-manager plugin, posts cap at ~17/100 SEO
score because Rank Math's meta isn't exposed to the REST API. With the
plugin, we can `POST /wp-json/rank-math-api/v1/updateMeta` per post and hit
80+ on first review.

This module produces the plugin-call PAYLOAD. The agent makes the actual
HTTP call (or the GH Actions Path B push does). Pure data transform.

Plugin docs: https://github.com/Devora-AS/rank-math-api-manager
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .identities import SITE_BASE_URL

RANK_MATH_ENDPOINT_PATH: Final[str] = "/wp-json/rank-math-api/v1/updateMeta"


@dataclass(frozen=True)
class RankMathMeta:
    """The four fields the Devora plugin endpoint accepts."""

    focus_keyword: str
    seo_title: str
    meta_description: str
    canonical_url: str


def build_meta(
    *,
    focus_keyword: str,
    seo_title: str,
    meta_description: str,
    slug: str,
    site_base_url: str = SITE_BASE_URL,
) -> RankMathMeta:
    """Build a RankMathMeta record from the draft fields."""
    base = site_base_url.rstrip("/")
    canonical = f"{base}/{slug.strip('/')}/"
    return RankMathMeta(
        focus_keyword=focus_keyword.strip(),
        seo_title=seo_title.strip(),
        meta_description=meta_description.strip(),
        canonical_url=canonical,
    )


def to_payload(post_id: int, meta: RankMathMeta) -> dict[str, object]:
    """Build the request body for the Devora plugin endpoint.

    Endpoint: POST {host}/wp-json/rank-math-api/v1/updateMeta
    Auth: same WP Application Password as everything else.
    """
    return {
        "objectID": post_id,
        "objectType": "post",
        "meta": {
            "rank_math_focus_keyword": meta.focus_keyword,
            "rank_math_title": meta.seo_title,
            "rank_math_description": meta.meta_description,
            "rank_math_canonical_url": meta.canonical_url,
        },
    }


def endpoint_url(site_base_url: str = SITE_BASE_URL) -> str:
    return site_base_url.rstrip("/") + RANK_MATH_ENDPOINT_PATH
