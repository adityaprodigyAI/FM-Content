"""cannibalization — pre-draft duplicate-content gate.

Strict 4-rule gate against the published-content inventory. EVERY rule runs
deterministically — there is no "warn-only" mode for critical/high. The W20
bug was three of the four rules silently no-op'ing on a degraded snapshot;
this module's first action is `inventory.assert_complete()` to refuse to
run on degraded data.

Detection rules (most-severe-first; first hit wins):

  Rule 1 (critical): proposed.slug exact match against any inventory slug
                     OR proposed.canonical URL == any inventory URL
  Rule 2 (critical): proposed.focus_keyword exact match against any
                     post.focus_keyword OR any post.organic_keywords
  Rule 3 (high):     title token-set Jaccard >= 0.7 vs any inventory title
  Rule 4 (high):     focus-keyword bigram+trigram overlap >= 0.5 vs any
                     post.focus_keyword

Critical and high are hard-blocked. Medium/low surface as soft warnings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal

from .inventory import Inventory, PublishedPost

Severity = Literal["clear", "low", "medium", "high", "critical"]
RecommendedAction = Literal["proceed", "differentiate", "merge", "refresh", "block"]
Audience = Literal["done-for-you", "diy"]

TITLE_JACCARD_HIGH: Final[float] = 0.7
TITLE_JACCARD_MEDIUM: Final[float] = 0.5
KW_NGRAM_HIGH: Final[float] = 0.5
KW_NGRAM_MEDIUM: Final[float] = 0.35

_STOPWORDS: Final[frozenset[str]] = frozenset(
    {
        "a", "an", "and", "as", "at", "be", "by", "for", "from", "how", "in",
        "is", "it", "of", "on", "or", "the", "to", "with", "what", "why",
        "when", "are", "you", "your", "that", "this", "into", "out",
        "about", "above", "after", "before", "between", "during", "where",
        "who", "whom", "whose", "which", "while", "more", "most", "some",
        "any", "all", "no", "not", "than", "then", "they", "their", "them",
        "have", "has", "had", "does", "did", "do", "would", "should", "could",
        "may", "might", "must", "vs", "via",
        # Blog-title noise that inflates Jaccard if left in
        "complete", "guide", "real", "actually", "amazing", "ultimate",
        "powerful", "best", "right", "wrong", "smart", "smarter",
    }
)
_DASHES: Final[str] = "‐‑‒–—―−"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProposedTopic:
    """The topic about to be drafted. All fields required."""

    slug: str
    title: str
    focus_keyword: str
    category_id: int
    audience: Audience
    canonical_url: str | None = None  # if known (e.g., GSC ranking page)


@dataclass(frozen=True)
class OverlapMatch:
    matched_post: PublishedPost
    severity: Severity
    reason: str


@dataclass(frozen=True)
class CannibalizationVerdict:
    severity: Severity
    recommended_action: RecommendedAction
    matches: list[OverlapMatch] = field(default_factory=list)
    rationale: str = ""


class CannibalizationError(ValueError):
    """Raised when the gate refuses a topic in blocking mode."""

    def __init__(self, verdict: CannibalizationVerdict, *, topic: ProposedTopic) -> None:
        self.verdict = verdict
        self.topic = topic
        super().__init__(_format_block_message(verdict=verdict, topic=topic))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate(topic: ProposedTopic, inventory: Inventory) -> CannibalizationVerdict:
    """Evaluate `topic` against `inventory`. Returns the highest-severity verdict.

    Refuses to run if the inventory is degraded or stale (the structural fix
    for the W20 bug — degraded data MUST NOT silently produce 'clear' verdicts).
    """
    inventory.assert_fresh()
    inventory.assert_complete()

    matches: list[OverlapMatch] = []

    # --- Rule 1: slug / URL exact match (critical) -------------------------
    slug_norm = _normalize_slug(topic.slug)
    canonical_url_norm = _normalize_url(topic.canonical_url) if topic.canonical_url else None
    for post in inventory.posts:
        if _normalize_slug(post.slug) == slug_norm:
            matches.append(
                OverlapMatch(
                    matched_post=post,
                    severity="critical",
                    reason=f"slug exact match ({post.slug})",
                )
            )
        if canonical_url_norm and _normalize_url(post.url) == canonical_url_norm:
            matches.append(
                OverlapMatch(
                    matched_post=post,
                    severity="critical",
                    reason=f"canonical URL match ({post.url})",
                )
            )

    # --- Rule 2: focus_keyword exact match (critical) ----------------------
    fk_norm = _normalize_keyword(topic.focus_keyword)
    for post in inventory.posts:
        post_focus = _normalize_keyword(post.focus_keyword or "")
        if fk_norm and post_focus and fk_norm == post_focus:
            matches.append(
                OverlapMatch(
                    matched_post=post,
                    severity="critical",
                    reason=(
                        f"focus_keyword {topic.focus_keyword!r} exact-matches "
                        f"#{post.id} focus_keyword"
                    ),
                )
            )
        for organic in post.organic_keywords:
            if fk_norm and _normalize_keyword(organic) == fk_norm:
                matches.append(
                    OverlapMatch(
                        matched_post=post,
                        severity="critical",
                        reason=(
                            f"focus_keyword {topic.focus_keyword!r} exact-matches "
                            f"#{post.id} organic keyword {organic!r}"
                        ),
                    )
                )

    # --- Rule 3: title token-set Jaccard (high) ----------------------------
    proposed_title_tokens = _title_tokens(topic.title)
    for post in inventory.posts:
        post_tokens = _title_tokens(post.title)
        if not proposed_title_tokens or not post_tokens:
            continue
        jacc = _jaccard(proposed_title_tokens, post_tokens)
        if jacc >= TITLE_JACCARD_HIGH:
            matches.append(
                OverlapMatch(
                    matched_post=post,
                    severity="high",
                    reason=f"title token-set Jaccard {jacc:.2f} >= {TITLE_JACCARD_HIGH}",
                )
            )
        elif jacc >= TITLE_JACCARD_MEDIUM:
            matches.append(
                OverlapMatch(
                    matched_post=post,
                    severity="medium",
                    reason=f"title token-set Jaccard {jacc:.2f}",
                )
            )

    # --- Rule 4: focus-kw n-gram overlap (high) ----------------------------
    proposed_ngrams = _bigrams_trigrams(topic.focus_keyword)
    for post in inventory.posts:
        post_ngrams = _bigrams_trigrams(post.focus_keyword or "")
        if not proposed_ngrams or not post_ngrams:
            continue
        overlap = _jaccard(proposed_ngrams, post_ngrams)
        if overlap >= KW_NGRAM_HIGH:
            matches.append(
                OverlapMatch(
                    matched_post=post,
                    severity="high",
                    reason=f"focus-kw n-gram overlap {overlap:.2f} >= {KW_NGRAM_HIGH}",
                )
            )
        elif overlap >= KW_NGRAM_MEDIUM:
            matches.append(
                OverlapMatch(
                    matched_post=post,
                    severity="medium",
                    reason=f"focus-kw n-gram overlap {overlap:.2f}",
                )
            )

    # --- Roll up ------------------------------------------------------------
    if not matches:
        return CannibalizationVerdict(
            severity="clear",
            recommended_action="proceed",
            matches=[],
            rationale="no overlap detected against current inventory",
        )

    severity = _max_severity(matches)
    return CannibalizationVerdict(
        severity=severity,
        recommended_action=_recommend(severity),
        matches=matches[:5],  # surface top 5 in the verdict for the slate notes
        rationale=_describe(severity, matches),
    )


def evaluate_or_block(topic: ProposedTopic, inventory: Inventory) -> CannibalizationVerdict:
    """Like `evaluate()`, but raises `CannibalizationError` on critical/high."""
    verdict = evaluate(topic, inventory)
    if verdict.severity in ("critical", "high"):
        raise CannibalizationError(verdict, topic=topic)
    return verdict


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _max_severity(matches: list[OverlapMatch]) -> Severity:
    order: dict[Severity, int] = {
        "clear": 0, "low": 1, "medium": 2, "high": 3, "critical": 4,
    }
    return max((m.severity for m in matches), key=lambda s: order[s])


def _recommend(severity: Severity) -> RecommendedAction:
    return {
        "critical": "block",
        "high": "block",
        "medium": "differentiate",
        "low": "proceed",
        "clear": "proceed",
    }[severity]


def _describe(severity: Severity, matches: list[OverlapMatch]) -> str:
    head = f"{severity}: {len(matches)} match(es)"
    top = matches[0]
    return f"{head} | {top.reason} (post #{top.matched_post.id} {top.matched_post.url})"


def _format_block_message(*, verdict: CannibalizationVerdict, topic: ProposedTopic) -> str:
    head = f"Cannibalization gate refused topic {topic.slug!r}: {verdict.rationale}"
    matches = "; ".join(
        f"#{m.matched_post.id} ({m.matched_post.slug}) — {m.reason}"
        for m in verdict.matches[:3]
    )
    if matches:
        return f"{head} | overlaps with: {matches}"
    return head


def _normalize_slug(slug: str) -> str:
    s = (slug or "").strip().lower()
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def _normalize_keyword(kw: str) -> str:
    if not kw:
        return ""
    s = kw.lower().strip()
    for d in _DASHES:
        s = s.replace(d, " ")
    s = s.replace("-", " ").replace("_", " ").replace("/", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    out = url.strip().lower().split("?", 1)[0].split("#", 1)[0]
    if not out.endswith("/"):
        out += "/"
    return out


def _title_tokens(title: str) -> set[str]:
    if not title:
        return set()
    s = title.lower()
    for d in _DASHES:
        s = s.replace(d, " ")
    words = re.findall(r"[a-z][a-z0-9'\-]+", s)
    return {w for w in words if w not in _STOPWORDS and len(w) > 2}


def _bigrams_trigrams(text: str) -> set[str]:
    if not text:
        return set()
    tokens = re.findall(r"[a-z0-9]+", _normalize_keyword(text))
    if len(tokens) < 2:
        return set()
    out: set[str] = set()
    for i in range(len(tokens) - 1):
        out.add(f"{tokens[i]} {tokens[i + 1]}")
    for i in range(len(tokens) - 2):
        out.add(f"{tokens[i]} {tokens[i + 1]} {tokens[i + 2]}")
    return out


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0
