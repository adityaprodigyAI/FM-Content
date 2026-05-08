"""Internal link selection for blog drafts.

Per the rubric:
- Cross-link blogs and Tier-1 landing pages
- All content prioritizes consulting conversions over Labs (audience routing)

Returns 3-5 internal links to drop into a new blog draft, biased toward the
audience tier (a `done-for-you` blog cross-links primarily to /consulting/
and other consulting-tier blogs).

When new blogs are published, append them to TIER_2_BLOGS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Audience = Literal["done-for-you", "diy"]


@dataclass(frozen=True)
class InternalLink:
    anchor: str
    url: str
    audience: Audience
    is_tier1: bool


TIER_1_PAGES: Final[tuple[InternalLink, ...]] = (
    InternalLink(
        anchor="AI consulting for small business",
        url="https://firstmovers.ai/ai-consulting-for-small-business/",
        audience="done-for-you",
        is_tier1=True,
    ),
    InternalLink(
        anchor="AI workflow automation",
        url="https://firstmovers.ai/ai-workflow-automation/",
        audience="done-for-you",
        is_tier1=True,
    ),
    InternalLink(
        anchor="agentic AI for sales",
        url="https://firstmovers.ai/agentic-ai-for-sales/",
        audience="done-for-you",
        is_tier1=True,
    ),
    InternalLink(
        anchor="AI implementation services",
        url="https://firstmovers.ai/ai-implementation-services/",
        audience="done-for-you",
        is_tier1=True,
    ),
    InternalLink(
        anchor="marketing automation with AI",
        url="https://firstmovers.ai/marketing-automation-ai/",
        audience="done-for-you",
        is_tier1=True,
    ),
    InternalLink(
        anchor="AI Labs",
        url="https://firstmovers.ai/labs/",
        audience="diy",
        is_tier1=True,
    ),
    InternalLink(
        anchor="our consulting offer",
        url="https://firstmovers.ai/consulting/",
        audience="done-for-you",
        is_tier1=True,
    ),
)

TIER_2_BLOGS: Final[tuple[InternalLink, ...]] = (
    InternalLink(
        anchor="how much AI consulting actually costs in 2026",
        url="https://firstmovers.ai/blog/ai-consulting-cost-2026/",
        audience="done-for-you",
        is_tier1=False,
    ),
    InternalLink(
        anchor="why ChatGPT alone isn't moving the needle",
        url="https://firstmovers.ai/blog/chatgpt-not-working/",
        audience="done-for-you",
        is_tier1=False,
    ),
    InternalLink(
        anchor="agentic AI explained",
        url="https://firstmovers.ai/blog/agentic-ai-explained/",
        audience="done-for-you",
        is_tier1=False,
    ),
    InternalLink(
        anchor="why most AI implementations stall",
        url="https://firstmovers.ai/blog/ai-implementation-not-working/",
        audience="done-for-you",
        is_tier1=False,
    ),
    InternalLink(
        anchor="connecting AI tools into a real workflow",
        url="https://firstmovers.ai/blog/connect-ai-tools-workflows/",
        audience="diy",
        is_tier1=False,
    ),
    InternalLink(
        anchor="AI-powered email automation",
        url="https://firstmovers.ai/blog/email-automation/",
        audience="diy",
        is_tier1=False,
    ),
    InternalLink(
        anchor="AI for sales teams",
        url="https://firstmovers.ai/blog/ai-for-sales-teams/",
        audience="done-for-you",
        is_tier1=False,
    ),
)


def select(
    audience: Audience,
    exclude_url: str | None = None,
    max_total: int = 5,
) -> list[InternalLink]:
    """Pick 3-5 internal links biased toward the requested audience.

    Guarantees:
      - At least one Tier-1 page matching the audience.
      - The currently-being-drafted post (exclude_url) is never linked.
      - Returns at most `max_total` links; never returns the same URL twice.
    """
    if max_total < 3:
        raise ValueError("max_total must be >= 3 to satisfy minimum link rule")

    pool = TIER_1_PAGES + TIER_2_BLOGS
    candidates = [link for link in pool if link.url != exclude_url]

    def score(link: InternalLink) -> tuple[int, int]:
        same_audience = 0 if link.audience == audience else 1
        tier_priority = 0 if link.is_tier1 else 1
        return (same_audience, tier_priority)

    ranked = sorted(candidates, key=score)

    matching_tier1 = [
        link for link in ranked if link.is_tier1 and link.audience == audience
    ]
    if not matching_tier1:
        matching_tier1 = [link for link in ranked if link.is_tier1][:1]

    selected: list[InternalLink] = []
    seen_urls: set[str] = set()

    for link in matching_tier1[:1] + ranked:
        if link.url in seen_urls:
            continue
        selected.append(link)
        seen_urls.add(link.url)
        if len(selected) >= max_total:
            break

    if len(selected) < 3:
        raise RuntimeError(
            f"Could not select 3+ internal links (got {len(selected)}). "
            "Check TIER_1_PAGES + TIER_2_BLOGS data."
        )
    return selected
