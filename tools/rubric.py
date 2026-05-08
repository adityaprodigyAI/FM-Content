"""rubric — hard-fail validators for blog drafts.

Every rule here ties back to a specific failure mode (Rank Math grading
penalty, Josh review rejection, or schema-conflict bug). When a validator
raises, fix the prose. Never silence — silence is how the v5 pipeline
shipped drafts that didn't meet the bar.

Validators are pure: they read a `Draft` dataclass and either return None
or raise `RubricViolation` with a message naming the rule.

Usage:

    from tools.rubric import Draft, validate

    draft = Draft(
        title="...",
        seo_title="...",
        meta_description="...",
        focus_keyword="...",
        slug="...",
        category_id=27,
        audience="done-for-you",
        body_html="...",       # final HTML body
        faq_items=[...],       # >=3 FaqItem records
        image_alts=["..."],    # alt text of every <img> in body order
    )
    validate(draft)            # raises RubricViolation on any failed rule
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal

from .external_links import is_external
from .identities import VALID_WP_CATEGORY_IDS

Audience = Literal["done-for-you", "diy"]


# ---------------------------------------------------------------------------
# Public exception + dataclass
# ---------------------------------------------------------------------------


class RubricViolation(ValueError):
    """Raised when a draft fails any validator. Message names the rule."""

    def __init__(self, rule: str, message: str) -> None:
        self.rule = rule
        super().__init__(f"[{rule}] {message}")


@dataclass(frozen=True)
class FaqItem:
    question: str
    answer: str


@dataclass(frozen=True)
class Draft:
    title: str
    seo_title: str
    meta_description: str
    focus_keyword: str
    slug: str
    category_id: int
    audience: Audience
    body_html: str
    faq_items: list[FaqItem] = field(default_factory=list)
    image_alts: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants — calibrated to the rubric (firstmovers-blog-rubric/SKILL.md)
# ---------------------------------------------------------------------------

MIN_WORD_COUNT: Final[int] = 2000  # production target 2,500
MAX_WORD_COUNT: Final[int] = 20_000
MIN_H2_COUNT: Final[int] = 6
MIN_IMAGE_COUNT: Final[int] = 3
MIN_EXTERNAL_LINK_COUNT: Final[int] = 3
MIN_FAQ_COUNT: Final[int] = 3
MAX_FAQ_COUNT: Final[int] = 8
MAX_POST_TITLE_CHARS: Final[int] = 120
MAX_SEO_TITLE_CHARS: Final[int] = 60
MAX_META_DESCRIPTION_CHARS: Final[int] = 155

FORBIDDEN_PHRASES: Final[tuple[str, ...]] = (
    "free audit",
)

# All Unicode dash variants. Hyphen-minus (U+002D) is allowed; everything
# else (en-dash, em-dash, figure dash, minus sign, etc.) is forbidden per
# Josh April 2026 directive.
FORBIDDEN_DASHES: Final[str] = "‐‑‒–—―−"

# Power words — at least one MUST appear in the SEO title. Curated subset
# of Rank Math's official list, biased toward operator-credible terms.
POWER_WORDS: Final[frozenset[str]] = frozenset(
    {
        "proven", "definitive", "essential", "complete", "comprehensive",
        "ultimate", "official", "authoritative", "reliable", "trusted",
        "practical", "actionable", "effective", "powerful", "smart",
        "strategic", "rigorous", "tested",
        "surprising", "shocking", "hidden", "secret", "untold", "insider",
        "revealed", "exposed", "uncovered", "breakthrough", "remarkable",
        "fast", "instant", "quick", "rapid", "lightning",
        "best", "top", "elite", "premier", "leading", "killer", "brilliant",
        "stunning", "incredible", "amazing", "genius", "unbeatable",
        "unstoppable", "bulletproof", "foolproof", "ironclad",
        "free", "cheap", "affordable", "lucrative", "valuable",
        "easy", "simple", "effortless", "seamless", "painless",
        "honest", "real", "true", "raw",
    }
)

# Audience -> required CTA destination URL substring (a CTA must contain it)
_AUDIENCE_TO_CTA_URL: Final[dict[Audience, str]] = {
    "done-for-you": "/consulting/",
    "diy": "/labs/",
}

# Audience -> forbidden CTA destination (the OTHER tier's URL must not appear
# as the primary CTA destination — cross-routing was a v5 review failure)
_AUDIENCE_TO_FORBIDDEN_CTA: Final[dict[Audience, str]] = {
    "done-for-you": "/labs/",
    "diy": "/consulting/",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<[^>]+>")
_H2_RE: Final[re.Pattern[str]] = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)
_H1_RE: Final[re.Pattern[str]] = re.compile(r"<h1\b", re.IGNORECASE)
_IMG_RE: Final[re.Pattern[str]] = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HREF_RE: Final[re.Pattern[str]] = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_AFFILIATE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"\[AFFILIATE_LINK:[^\]]+\]")
_NOFOLLOW_RE: Final[re.Pattern[str]] = re.compile(
    r'<a\b[^>]*\brel="[^"]*\bnofollow\b[^"]*"[^>]*>', re.IGNORECASE
)
_BLOG_POSTING_JSONLD_RE: Final[re.Pattern[str]] = re.compile(
    r'"@type"\s*:\s*"BlogPosting"', re.IGNORECASE
)
_BREADCRUMB_JSONLD_RE: Final[re.Pattern[str]] = re.compile(
    r'"@type"\s*:\s*"BreadcrumbList"', re.IGNORECASE
)


def _strip_tags(html: str) -> str:
    return _TAG_RE.sub(" ", html)


def _word_count(html: str) -> int:
    plain = _strip_tags(html)
    return len([w for w in plain.split() if w.strip()])


def _h2_texts(html: str) -> list[str]:
    return [_TAG_RE.sub(" ", m.group(1)).strip() for m in _H2_RE.finditer(html)]


def _img_count(html: str) -> int:
    return len(_IMG_RE.findall(html))


def _hrefs(html: str) -> list[str]:
    return _HREF_RE.findall(html)


def _contains_kw(haystack: str, focus_keyword: str) -> bool:
    """Case-insensitive substring; tolerates hyphenation differences."""
    if not focus_keyword:
        return False
    norm = lambda s: re.sub(r"[\s\-_]+", " ", s.lower()).strip()
    return norm(focus_keyword) in norm(haystack)


# ---------------------------------------------------------------------------
# Validators (each one raises RubricViolation on failure)
# ---------------------------------------------------------------------------


def _validate_category(d: Draft) -> None:
    if d.category_id not in VALID_WP_CATEGORY_IDS:
        raise RubricViolation(
            "category",
            f"category_id={d.category_id} not in {sorted(VALID_WP_CATEGORY_IDS)}",
        )


def _validate_audience(d: Draft) -> None:
    if d.audience not in ("done-for-you", "diy"):
        raise RubricViolation("audience", f"unknown audience {d.audience!r}")


def _validate_title(d: Draft) -> None:
    if not d.title.strip():
        raise RubricViolation("title", "post title is empty")
    if len(d.title) > MAX_POST_TITLE_CHARS:
        raise RubricViolation(
            "title",
            f"post title is {len(d.title)} chars (max {MAX_POST_TITLE_CHARS})",
        )
    if d.title.rstrip().endswith("."):
        raise RubricViolation("title", "post title ends in a period — strip it")
    if any(ch in d.title for ch in FORBIDDEN_DASHES):
        raise RubricViolation("title", "post title contains a forbidden dash variant (use hyphens only)")


def _validate_seo_title(d: Draft) -> None:
    if not d.seo_title.strip():
        raise RubricViolation("seo_title", "seo_title is empty")
    if len(d.seo_title) > MAX_SEO_TITLE_CHARS:
        raise RubricViolation(
            "seo_title",
            f"seo_title is {len(d.seo_title)} chars (max {MAX_SEO_TITLE_CHARS})",
        )
    if not _contains_kw(d.seo_title, d.focus_keyword):
        raise RubricViolation(
            "seo_title_focus_keyword",
            f"seo_title does not contain focus_keyword {d.focus_keyword!r}",
        )
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]+", d.seo_title.lower())
    if not any(w in POWER_WORDS for w in words):
        raise RubricViolation(
            "seo_title_power_word",
            f"seo_title contains no power word from POWER_WORDS. seo_title={d.seo_title!r}",
        )


def _validate_meta_description(d: Draft) -> None:
    if not d.meta_description.strip():
        raise RubricViolation("meta_description", "meta_description is empty")
    if len(d.meta_description) > MAX_META_DESCRIPTION_CHARS:
        raise RubricViolation(
            "meta_description",
            f"meta_description is {len(d.meta_description)} chars (max {MAX_META_DESCRIPTION_CHARS})",
        )
    if not _contains_kw(d.meta_description, d.focus_keyword):
        raise RubricViolation(
            "meta_description_focus_keyword",
            f"meta_description does not contain focus_keyword {d.focus_keyword!r}",
        )


def _validate_slug(d: Draft) -> None:
    if not d.slug or not re.match(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$", d.slug):
        raise RubricViolation("slug", f"slug {d.slug!r} is empty or non-canonical")
    if not _contains_kw(d.slug.replace("-", " "), d.focus_keyword):
        raise RubricViolation(
            "slug_focus_keyword",
            f"slug {d.slug!r} does not contain focus_keyword {d.focus_keyword!r}",
        )


def _validate_word_count(d: Draft) -> None:
    wc = _word_count(d.body_html)
    if wc < MIN_WORD_COUNT:
        raise RubricViolation(
            "word_count",
            f"body has {wc} words; minimum is {MIN_WORD_COUNT} (target 2,500)",
        )
    if wc > MAX_WORD_COUNT:
        raise RubricViolation(
            "word_count", f"body has {wc} words; maximum is {MAX_WORD_COUNT}"
        )


def _validate_h2(d: Draft) -> None:
    h2s = _h2_texts(d.body_html)
    if len(h2s) < MIN_H2_COUNT:
        raise RubricViolation(
            "h2_count",
            f"body has {len(h2s)} H2 sections; minimum is {MIN_H2_COUNT}",
        )
    if not any(_contains_kw(h, d.focus_keyword) for h in h2s):
        raise RubricViolation(
            "h2_focus_keyword",
            f"no H2 contains focus_keyword {d.focus_keyword!r}; h2s={h2s}",
        )


def _validate_no_h1(d: Draft) -> None:
    if _H1_RE.search(d.body_html):
        raise RubricViolation(
            "no_h1_in_body",
            "body contains a leading <h1> — WP themes render the post title as the H1",
        )


def _validate_images(d: Draft) -> None:
    if _img_count(d.body_html) < MIN_IMAGE_COUNT:
        raise RubricViolation(
            "image_count",
            f"body has {_img_count(d.body_html)} <img> tags; minimum is {MIN_IMAGE_COUNT}",
        )
    if not any(_contains_kw(alt, d.focus_keyword) for alt in d.image_alts):
        raise RubricViolation(
            "image_alt_focus_keyword",
            f"no image alt contains focus_keyword {d.focus_keyword!r}; "
            f"alts={d.image_alts}",
        )


def _validate_external_links(d: Draft) -> None:
    """Body must have >= MIN_EXTERNAL_LINK_COUNT external dofollow links.

    Pexels photographer attribution links are correctly marked rel=nofollow
    per the Pexels API license — those don't count as citations and don't
    fail this validator. We count only external links WITHOUT nofollow as
    citations, then require >= 3 of those.
    """
    dofollow_external = 0
    for tag in re.finditer(r'<a\b[^>]*\bhref="([^"]+)"[^>]*>', d.body_html):
        href = tag.group(1)
        if not is_external(href):
            continue
        full = tag.group(0)
        is_nofollow = bool(
            re.search(r'\brel="[^"]*\bnofollow\b', full, re.IGNORECASE)
        )
        if not is_nofollow:
            dofollow_external += 1
    if dofollow_external < MIN_EXTERNAL_LINK_COUNT:
        raise RubricViolation(
            "external_links",
            f"body has {dofollow_external} external dofollow links; minimum is "
            f"{MIN_EXTERNAL_LINK_COUNT} (Pexels attribution rel=nofollow links "
            "don't count as citations)",
        )


def _validate_no_forbidden_phrases(d: Draft) -> None:
    body_lower = d.body_html.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in body_lower:
            raise RubricViolation(
                "forbidden_phrase",
                f"body contains forbidden phrase {phrase!r}",
            )


def _validate_no_em_dashes(d: Draft) -> None:
    for ch in FORBIDDEN_DASHES:
        if ch in d.body_html:
            raise RubricViolation(
                "no_em_dashes",
                f"body contains forbidden dash variant U+{ord(ch):04X} (use hyphens only)",
            )


def _validate_no_affiliate_tokens(d: Draft) -> None:
    if _AFFILIATE_TOKEN_RE.search(d.body_html):
        raise RubricViolation(
            "affiliate_token_leak",
            "body contains [AFFILIATE_LINK:X] placeholder; replace with a real URL or remove",
        )


def _validate_no_extra_jsonld(d: Draft) -> None:
    """Reject manually-emitted BlogPosting / BreadcrumbList JSON-LD.

    Rank Math emits both at render time; manual emission causes schema
    duplication that Google's rich-results test flags.
    """
    if _BLOG_POSTING_JSONLD_RE.search(d.body_html):
        raise RubricViolation(
            "extra_jsonld_blogposting",
            "body contains BlogPosting JSON-LD; Rank Math emits this at render time",
        )
    if _BREADCRUMB_JSONLD_RE.search(d.body_html):
        raise RubricViolation(
            "extra_jsonld_breadcrumb",
            "body contains BreadcrumbList JSON-LD; Rank Math emits this at render time",
        )


def _validate_faq(d: Draft) -> None:
    n = len(d.faq_items)
    if n < MIN_FAQ_COUNT:
        raise RubricViolation(
            "faq_count",
            f"FAQ has {n} items; minimum is {MIN_FAQ_COUNT}",
        )
    if n > MAX_FAQ_COUNT:
        raise RubricViolation(
            "faq_count",
            f"FAQ has {n} items; maximum is {MAX_FAQ_COUNT}",
        )


def _validate_lede_focus_keyword(d: Draft) -> None:
    """Focus keyword must appear in the first ~10% of the body (the lede)."""
    plain = _strip_tags(d.body_html)
    head_chars = max(800, int(len(plain) * 0.10))
    head = plain[:head_chars]
    if not _contains_kw(head, d.focus_keyword):
        raise RubricViolation(
            "lede_focus_keyword",
            f"focus_keyword {d.focus_keyword!r} not found in first ~{head_chars} chars of body",
        )


def _validate_cta_routing(d: Draft) -> None:
    """The audience-required CTA URL substring must appear in the body."""
    required = _AUDIENCE_TO_CTA_URL[d.audience]
    if required not in d.body_html:
        raise RubricViolation(
            "cta_routing",
            f"audience={d.audience} requires a CTA pointing to {required!r}",
        )


def _validate_status_draft_only(d: Draft) -> None:
    """The body must not embed publish-status hints. The push layer always
    sets status=draft, but we guard against shortcut prompts.
    """
    if "<!-- status: publish" in d.body_html.lower():
        raise RubricViolation(
            "status_draft_only",
            "body marker requests publish status; only Nikki publishes",
        )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


_VALIDATORS = (
    _validate_category,
    _validate_audience,
    _validate_title,
    _validate_seo_title,
    _validate_meta_description,
    _validate_slug,
    _validate_word_count,
    _validate_h2,
    _validate_no_h1,
    _validate_images,
    _validate_external_links,
    _validate_no_forbidden_phrases,
    _validate_no_em_dashes,
    _validate_no_affiliate_tokens,
    _validate_no_extra_jsonld,
    _validate_faq,
    _validate_lede_focus_keyword,
    _validate_cta_routing,
    _validate_status_draft_only,
)


def validate(draft: Draft) -> None:
    """Run every validator. Raises `RubricViolation` on the first failure.

    Order matters: cheaper structural checks (category, title length) run
    before content checks (word count, H2 scan).
    """
    for v in _VALIDATORS:
        v(draft)
