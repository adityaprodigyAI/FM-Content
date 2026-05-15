"""JSON-LD schema builders for blog posts.

Per the rubric, every blog embeds **FAQPage** JSON-LD only. Rank Math emits
BlogPosting + BreadcrumbList at render time — duplicating them in the body
causes schema conflicts.

The blog_posting() and breadcrumb_list() builders are kept here for
completeness and for any one-off use, but draft.assemble() must NOT inject
them into the body.

Validate sample output against:
  https://validator.schema.org/
  https://search.google.com/test/rich-results
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .identities import BRAND_NAME, SITE_BASE_URL


@dataclass(frozen=True)
class FaqItem:
    question: str
    answer: str  # plain text or HTML; will be JSON-encoded


def faq_page(faq: list[FaqItem]) -> dict[str, Any]:
    """Build a schema.org/FAQPage JSON-LD object from FAQ items."""
    if not faq:
        raise ValueError("FAQPage requires at least one FaqItem")
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": item.question,
                "acceptedAnswer": {"@type": "Answer", "text": item.answer},
            }
            for item in faq
        ],
    }


def blog_posting(
    *,
    title: str,
    description: str,
    canonical_url: str,
    author_name: str = "Josh McCoy",
    author_url: str = f"{SITE_BASE_URL}/author/websitegenius/",
    publisher_name: str = BRAND_NAME,
    publisher_url: str = SITE_BASE_URL,
    publisher_logo_url: str = (
        f"{SITE_BASE_URL}/wp-content/uploads/2024/01/first-movers-logo.png"
    ),
    date_published: str,
    date_modified: str | None = None,
    image_url: str | None = None,
) -> dict[str, Any]:
    """Build a schema.org/BlogPosting JSON-LD object.

    DO NOT inject the result into the body — Rank Math emits BlogPosting at
    render time and duplicate emission breaks rich-result eligibility. Kept
    here for one-off / debugging use.
    """
    obj: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": title,
        "description": description,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical_url},
        "url": canonical_url,
        "author": {"@type": "Person", "name": author_name, "url": author_url},
        "publisher": {
            "@type": "Organization",
            "name": publisher_name,
            "url": publisher_url,
            "logo": {"@type": "ImageObject", "url": publisher_logo_url},
        },
        "datePublished": date_published,
        "dateModified": date_modified or date_published,
    }
    if image_url:
        obj["image"] = {"@type": "ImageObject", "url": image_url}
    return obj


def breadcrumb_list(
    *,
    blog_title: str,
    canonical_url: str,
    site_base_url: str = SITE_BASE_URL,
) -> dict[str, Any]:
    """Build a 3-level breadcrumb. Same warning as blog_posting()."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": site_base_url},
            {"@type": "ListItem", "position": 2, "name": "Blog", "item": f"{site_base_url}/blog/"},
            {"@type": "ListItem", "position": 3, "name": blog_title, "item": canonical_url},
        ],
    }


def render_html(blocks: list[dict[str, Any]]) -> str:
    """Wrap a list of JSON-LD dicts in <script> tags, ready to append to body."""
    chunks = []
    for block in blocks:
        encoded = json.dumps(block, ensure_ascii=False, indent=2)
        chunks.append(
            f'<script type="application/ld+json">\n{encoded}\n</script>'
        )
    return "\n".join(chunks)
