"""External-link allowlist for blog drafts.

Rank Math grades two checks tied to outbound links:
  - "Linking to External Sources" — at least one external link present
  - "Linking to External Content with Followed Link" — at least one is dofollow

Together those checks alone account for ~10 points of the 0-100 SEO score.
Beyond Rank Math, citing authoritative third-party sources improves topical
authority and AEO (AI engine optimization) — Searchable, Perplexity, and
ChatGPT all weight outbound citations when picking which posts to cite.

Curated allowlist per category. Every URL must be:
  1. Owned by a credible, durable domain (industry research firm, academic
     institution, government org, or top-tier journalism). No vendor blogs
     unless the vendor is genuinely the primary source.
  2. Stable. Prefer domain-roots over deep dated URLs that 404 in two years.
  3. Topically aligned with the blog category. Generic AI URLs go in
     `EVERGREEN` and apply as fallback.

Excluded competitors (do not cite or link): PwC, Accenture, Capgemini, IBM.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from .identities import (
    SITE_HOST,
    VALID_WP_CATEGORY_IDS,
    WP_CATEGORY_AGI,
    WP_CATEGORY_AI_AUTOMATION,
    WP_CATEGORY_AI_CONSULTING,
    WP_CATEGORY_AI_IN_BUSINESS,
    WP_CATEGORY_AI_MARKETING,
    WP_CATEGORY_AI_SALES,
    WP_CATEGORY_AI_TOOLS,
)

# The client's own host(s) — a self-citation is never a valid "external" link.
# Sourced from client_config.toml [brand].site_host via identities.
INTERNAL_HOSTS: Final[frozenset[str]] = frozenset(
    {SITE_HOST, f"www.{SITE_HOST}"}
)


@dataclass(frozen=True)
class ExternalLink:
    url: str
    anchor_hint: str
    why: str


EVERGREEN: Final[tuple[ExternalLink, ...]] = (
    ExternalLink(
        url="https://hbr.org/topic/subject/artificial-intelligence",
        anchor_hint="Harvard Business Review on AI",
        why="HBR is the canonical executive-decision-maker source on AI strategy.",
    ),
    ExternalLink(
        url="https://www.mckinsey.com/capabilities/quantumblack/our-insights",
        anchor_hint="McKinsey QuantumBlack research",
        why="McKinsey's annual State of AI report is one of the most cited operator surveys.",
    ),
    ExternalLink(
        url="https://hai.stanford.edu/research",
        anchor_hint="Stanford HAI research",
        why="Stanford HAI publishes the AI Index Report — the most rigorous public AI benchmark.",
    ),
    ExternalLink(
        url="https://www.technologyreview.com/topic/artificial-intelligence/",
        anchor_hint="MIT Technology Review on AI",
        why="MIT Tech Review covers the technical and societal dimensions of AI deployment.",
    ),
    ExternalLink(
        url="https://www.gartner.com/en/topics/artificial-intelligence",
        anchor_hint="Gartner research on AI",
        why="Gartner's Hype Cycle and Magic Quadrant are referenced by buyers shortlisting vendors.",
    ),
)


_AI_CONSULTING_SOURCES: tuple[ExternalLink, ...] = (
    ExternalLink(
        url="https://www.bcg.com/capabilities/artificial-intelligence",
        anchor_hint="BCG on AI consulting",
        why="BCG's Build for the Future report tracks how leading firms use AI consulting.",
    ),
    ExternalLink(
        url="https://www.bain.com/insights/topics/artificial-intelligence/",
        anchor_hint="Bain insights on AI",
        why="Bain publishes pricing benchmarks and case-study breakdowns of AI engagements.",
    ),
)


_AI_AUTOMATION_SOURCES: tuple[ExternalLink, ...] = (
    ExternalLink(
        url="https://www.mckinsey.com/featured-insights/future-of-work",
        anchor_hint="McKinsey Future of Work",
        why="McKinsey's 'A future that works' report is the canonical source on automation potential.",
    ),
    ExternalLink(
        url="https://www3.weforum.org/docs/WEF_Future_of_Jobs_Report_2023.pdf",
        anchor_hint="World Economic Forum Future of Jobs",
        why="WEF's biennial report quantifies automation displacement and creation by industry.",
    ),
    ExternalLink(
        url="https://sloanreview.mit.edu/topic/artificial-intelligence/",
        anchor_hint="MIT Sloan Management Review on AI",
        why="MIT Sloan publishes rigorous case studies of AI workflow automation in operations.",
    ),
)


_AI_SALES_SOURCES: tuple[ExternalLink, ...] = (
    ExternalLink(
        url="https://www.salesforce.com/resources/research-reports/state-of-sales/",
        anchor_hint="Salesforce State of Sales report",
        why="Salesforce surveys 5,500+ sales leaders annually on AI adoption and outcomes.",
    ),
    ExternalLink(
        url="https://www.hubspot.com/state-of-marketing",
        anchor_hint="HubSpot State of Marketing report",
        why="HubSpot's annual state-of report covers sales-marketing alignment and AI usage.",
    ),
    ExternalLink(
        url="https://www.gartner.com/en/sales/insights/artificial-intelligence",
        anchor_hint="Gartner sales AI research",
        why="Gartner's Sales Practice publishes vendor evaluations and adoption benchmarks.",
    ),
)


_AI_MARKETING_SOURCES: tuple[ExternalLink, ...] = (
    ExternalLink(
        url="https://www.hubspot.com/state-of-marketing",
        anchor_hint="HubSpot State of Marketing report",
        why="HubSpot tracks 1,200+ marketing leaders on AI usage and ROI year over year.",
    ),
    ExternalLink(
        url="https://www.mckinsey.com/capabilities/growth-marketing-and-sales/our-insights",
        anchor_hint="McKinsey Growth, Marketing & Sales insights",
        why="McKinsey's 'Next in Personalization' report quantifies AI-driven marketing lift.",
    ),
    ExternalLink(
        url="https://contentmarketinginstitute.com/articles/category/research/",
        anchor_hint="Content Marketing Institute research",
        why="CMI's annual B2B and B2C reports cover AI content workflows specifically.",
    ),
)


_AI_IN_BUSINESS_SOURCES: tuple[ExternalLink, ...] = (
    ExternalLink(
        url="https://www.weforum.org/agenda/archive/artificial-intelligence/",
        anchor_hint="World Economic Forum on AI",
        why="WEF's AI coverage is non-vendor, policy-grounded, and globally cited.",
    ),
    ExternalLink(
        url="https://www.oecd.org/digital/artificial-intelligence/",
        anchor_hint="OECD AI Policy Observatory",
        why="OECD AI publishes cross-country adoption data and government-grade guidance.",
    ),
    ExternalLink(
        url="https://www.bcg.com/publications/2023/scaling-ai-pays-off",
        anchor_hint="BCG on scaling AI",
        why="BCG's AI scaling research segments operators by maturity and quantifies revenue lift.",
    ),
)


_AI_TOOLS_SOURCES: tuple[ExternalLink, ...] = (
    ExternalLink(
        url="https://www.anthropic.com/news",
        anchor_hint="Anthropic announcements",
        why="Anthropic's news feed is the primary source for Claude model capabilities.",
    ),
    ExternalLink(
        url="https://openai.com/blog",
        anchor_hint="OpenAI blog",
        why="OpenAI's blog is the primary source for GPT model capabilities and usage patterns.",
    ),
    ExternalLink(
        url="https://www.theverge.com/ai-artificial-intelligence",
        anchor_hint="The Verge on AI",
        why="The Verge covers tool launches and real-world reviews from a journalist perspective.",
    ),
)


_AGI_SOURCES: tuple[ExternalLink, ...] = (
    ExternalLink(
        url="https://www.anthropic.com/research",
        anchor_hint="Anthropic research",
        why="Anthropic publishes alignment research central to AGI safety discussions.",
    ),
    ExternalLink(
        url="https://openai.com/research",
        anchor_hint="OpenAI research",
        why="OpenAI's research blog covers frontier-model capabilities and AGI roadmaps.",
    ),
    ExternalLink(
        url="https://deepmind.google/research/",
        anchor_hint="Google DeepMind research",
        why="DeepMind publishes long-horizon AGI research including Gemini and AlphaFold.",
    ),
)


_BY_CATEGORY: Final[dict[int, tuple[ExternalLink, ...]]] = {
    WP_CATEGORY_AI_CONSULTING: _AI_CONSULTING_SOURCES,
    WP_CATEGORY_AI_AUTOMATION: _AI_AUTOMATION_SOURCES,
    WP_CATEGORY_AI_SALES: _AI_SALES_SOURCES,
    WP_CATEGORY_AI_MARKETING: _AI_MARKETING_SOURCES,
    WP_CATEGORY_AI_IN_BUSINESS: _AI_IN_BUSINESS_SOURCES,
    WP_CATEGORY_AI_TOOLS: _AI_TOOLS_SOURCES,
    WP_CATEGORY_AGI: _AGI_SOURCES,
}


def curated_for(category_id: int, *, max_total: int = 5) -> list[ExternalLink]:
    """Return up to `max_total` curated external sources for the given category.

    Concatenates category-specific sources first, then EVERGREEN for fallback,
    deduped by URL. Raises ValueError if `category_id` is not a known category.
    """
    if category_id not in VALID_WP_CATEGORY_IDS:
        raise ValueError(
            f"category_id {category_id} not in known categories: "
            f"{sorted(VALID_WP_CATEGORY_IDS)}"
        )
    if max_total < 1:
        raise ValueError("max_total must be >= 1")

    primary = _BY_CATEGORY.get(category_id, ())
    pool = list(primary) + list(EVERGREEN)

    seen: set[str] = set()
    deduped: list[ExternalLink] = []
    for link in pool:
        if link.url in seen:
            continue
        seen.add(link.url)
        deduped.append(link)
        if len(deduped) >= max_total:
            break
    return deduped


def is_external(url: str) -> bool:
    """True iff `url` points at a host outside firstmovers.ai."""
    if not url:
        return False
    cleaned = url.strip().lower()
    if cleaned.startswith(("/", "#", "mailto:", "tel:")):
        return False
    if "://" not in cleaned:
        return False
    host = cleaned.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
    return host not in INTERNAL_HOSTS
