"""draft — Wednesday job: per-approved-title prose generation orchestration.

Python doesn't generate prose. Claude does. This module's job is to:

  1. Build the brief — the dict Claude needs to write a draft (focus_keyword,
     audience, category, internal links, external citations, target word
     count, FAQ topic seeds, hero image alt requirement).
  2. Re-run cannibalization (defense in depth — inventory may have grown
     since Sunday).
  3. Assemble the final body HTML from the agent-supplied prose pieces
     (markdown body + FAQ items + image refs).
  4. Run rubric.validate on the assembled draft.
  5. Hand the draft to push_wp.

Pure Python; no MCP calls. The Wednesday agent calls this module's helpers
in sequence around its own MCP calls + prose generation.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Final

from .cannibalization import ProposedTopic, evaluate_or_block
from .external_links import ExternalLink, curated_for
from .images import ImageRef, hero_alt, render_figure
from .internal_links import InternalLink, select as select_internal_links
from .inventory import Inventory
from .rubric import Draft, FaqItem, validate
from .schemas import faq_page, render_html as render_jsonld
from .slate import SlateProposal

DRAFTS_DIR: Final[Path] = (
    Path(__file__).resolve().parents[1] / "data" / "runs" / "_drafts"
)


# ---------------------------------------------------------------------------
# Brief — what Claude needs to write a draft
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DraftBrief:
    proposal: SlateProposal
    internal_links: list[InternalLink]
    external_citations: list[ExternalLink]
    target_word_count: int
    target_h2_count: int
    target_image_count: int
    cta_url: str
    forbidden_phrases: tuple[str, ...]


# Audience -> CTA URL is duplicated here from rubric for readability
_AUDIENCE_TO_CTA_URL: Final[dict[str, str]] = {
    "done-for-you": "https://firstmovers.ai/consulting/",
    "diy": "https://firstmovers.ai/labs/",
}


def prepare_brief(
    proposal: SlateProposal,
    inventory: Inventory,
    *,
    target_word_count: int = 2500,
    target_h2_count: int = 7,
    target_image_count: int = 4,
) -> DraftBrief:
    """Build the brief Claude uses when writing the prose.

    Re-runs cannibalization against the latest inventory; raises
    `CannibalizationError` if the topic flipped between Sunday and Wednesday.
    """
    inventory.assert_fresh()
    inventory.assert_complete()

    topic = ProposedTopic(
        slug=proposal.slug,
        title=proposal.working_title,
        focus_keyword=proposal.focus_keyword,
        category_id=proposal.category_id,
        audience=proposal.audience,  # type: ignore[arg-type]
    )
    evaluate_or_block(topic, inventory)  # raises on critical/high

    internal = select_internal_links(
        proposal.audience,  # type: ignore[arg-type]
        exclude_url=f"https://firstmovers.ai/{proposal.slug}/",
        max_total=5,
    )
    external = curated_for(proposal.category_id, max_total=6)

    return DraftBrief(
        proposal=proposal,
        internal_links=internal,
        external_citations=external,
        target_word_count=target_word_count,
        target_h2_count=target_h2_count,
        target_image_count=target_image_count,
        cta_url=_AUDIENCE_TO_CTA_URL[proposal.audience],
        forbidden_phrases=("free audit",),
    )


def render_brief_for_prompt(brief: DraftBrief) -> str:
    """Render the brief as a structured prompt that Claude can parse to write the draft.

    The Wednesday agent loads the firstmovers-blog-rubric skill, passes this
    string as input, and writes back the body markdown + FAQ items.
    """
    p = brief.proposal
    out = [
        f"# Brief: {p.working_title}",
        "",
        f"**Focus keyword:** {p.focus_keyword}",
        f"**Audience:** {p.audience}  ({brief.cta_url})",
        f"**Category id:** {p.category_id}",
        f"**Slug:** {p.slug}",
        f"**Target publish date:** {p.target_date}",
        "",
        f"**Angle:** {p.one_line_angle}",
        "",
        "**Outline (use as H2 starters; expand to ≥6 H2s):**",
    ]
    for bullet in p.outline_bullets:
        out.append(f"- {bullet}")
    out.extend([
        "",
        f"**Target:** {brief.target_word_count}w, {brief.target_h2_count} H2s, "
        f"{brief.target_image_count} images, ≥3 external dofollow links.",
        f"**Focus keyword must appear in:** lede, ≥1 H2, ≥1 image alt, slug, "
        f"seo_title, meta_description.",
        "",
        "**Internal links to weave (audience-routed):**",
    ])
    for link in brief.internal_links:
        out.append(f"- [{link.anchor}]({link.url})  ({link.audience})")
    out.append("")
    out.append("**External citations to draw from (any 3+ from this list):**")
    for cite in brief.external_citations:
        out.append(f"- {cite.anchor_hint} -> {cite.url}  -- {cite.why}")
    out.extend([
        "",
        f"**CTA:** end the body with a paragraph that links to {brief.cta_url}.",
        f"**Forbidden:** {', '.join(brief.forbidden_phrases)} (anywhere). "
        f"Em dashes (use hyphens). Trailing periods in titles. <h1> in body.",
        f"**JSON-LD:** emit FAQPage only. Rank Math handles BlogPosting + BreadcrumbList.",
        "",
        "Return:",
        "- `body_markdown`  (the full body content)",
        "- `faq_items`     (3-8 FaqItem records, question + answer)",
        "- `seo_title`     (≤60 chars, contains focus keyword + a power word)",
        "- `meta_description` (≤155 chars, contains focus keyword)",
    ])
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssembledDraft:
    """Everything the push layer needs to create a WP post + set Rank Math meta."""

    title: str
    seo_title: str
    meta_description: str
    focus_keyword: str
    slug: str
    category_id: int
    audience: str
    excerpt: str
    body_html: str
    faq_items: list[FaqItem]
    image_alts: list[str]
    proposal: SlateProposal


def assemble(
    brief: DraftBrief,
    *,
    body_html: str,
    faq_items: list[FaqItem],
    images: list[ImageRef],
    seo_title: str,
    meta_description: str,
    excerpt: str | None = None,
) -> AssembledDraft:
    """Assemble the final body and validate against the rubric.

    Inputs:
      - `body_html`  — the prose Claude wrote, already converted to HTML.
      - `faq_items`  — 3-8 FAQ entries Claude wrote.
      - `images`     — 4 ImageRef records Claude fetched from Pexels.
      - `seo_title` / `meta_description` — Claude's metadata.

    Output:
      - AssembledDraft with body_html that includes images + FAQ schema.
      - Raises `RubricViolation` if any rule fails.
    """
    if len(images) < 1:
        raise ValueError("assemble requires at least 1 image (the hero)")

    # Inject hero image at the top, with focus-keyword-bearing alt
    first_h2 = _first_h2_text(body_html) or brief.proposal.working_title
    hero = images[0]
    hero_alt_text = hero_alt(brief.proposal.focus_keyword, first_h2)
    hero_block = render_figure(hero, alt_override=hero_alt_text, is_hero=True)

    # Inject body images after every other H2
    body_with_images = _inject_body_images(body_html, images[1:])

    # FAQ JSON-LD (Rank Math emits BlogPosting + BreadcrumbList)
    schema_html = render_jsonld([faq_page([
        # Convert local FaqItem to schemas.FaqItem
        # (they have the same shape; we re-import locally to keep types clean)
        type("X", (), {"question": q.question, "answer": q.answer})()  # noqa: E721
        for q in faq_items
    ])]) if faq_items else ""

    # FAQ HTML section that humans + Rank Math both read
    faq_html = _render_faq_section(faq_items)

    final_body = "\n".join(
        s for s in [hero_block, body_with_images, faq_html, schema_html] if s
    )

    image_alts = [hero_alt_text] + [img.alt for img in images[1:]]

    draft = Draft(
        title=brief.proposal.working_title,
        seo_title=seo_title,
        meta_description=meta_description,
        focus_keyword=brief.proposal.focus_keyword,
        slug=brief.proposal.slug,
        category_id=brief.proposal.category_id,
        audience=brief.proposal.audience,  # type: ignore[arg-type]
        body_html=final_body,
        faq_items=[FaqItem(question=q.question, answer=q.answer) for q in faq_items],
        image_alts=image_alts,
    )
    validate(draft)  # raises RubricViolation on any rule failure

    return AssembledDraft(
        title=brief.proposal.working_title,
        seo_title=seo_title,
        meta_description=meta_description,
        focus_keyword=brief.proposal.focus_keyword,
        slug=brief.proposal.slug,
        category_id=brief.proposal.category_id,
        audience=brief.proposal.audience,
        excerpt=excerpt or _auto_excerpt(meta_description, brief.proposal.one_line_angle),
        body_html=final_body,
        faq_items=draft.faq_items,
        image_alts=image_alts,
        proposal=brief.proposal,
    )


# ---------------------------------------------------------------------------
# Persistence — Wednesday writes the assembled drafts to disk
# ---------------------------------------------------------------------------


def write_drafts(
    week: str,
    drafts: list[AssembledDraft],
    *,
    dir_: Path = DRAFTS_DIR,
) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    path = dir_ / f"{week}.json"
    payload = {
        "week": week,
        "drafts": [
            {
                "title": d.title,
                "seo_title": d.seo_title,
                "meta_description": d.meta_description,
                "focus_keyword": d.focus_keyword,
                "slug": d.slug,
                "category_id": d.category_id,
                "audience": d.audience,
                "excerpt": d.excerpt,
                "body_html": d.body_html,
                "faq_items": [{"question": f.question, "answer": f.answer} for f in d.faq_items],
                "image_alts": d.image_alts,
                "proposal": asdict(d.proposal),
            }
            for d in drafts
        ],
    }
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


import re

_H2_OPEN_RE: Final[re.Pattern[str]] = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.IGNORECASE | re.DOTALL)


def _first_h2_text(html: str) -> str | None:
    m = _H2_OPEN_RE.search(html)
    if not m:
        return None
    return re.sub(r"<[^>]+>", " ", m.group(1)).strip()


def _inject_body_images(html: str, images: list[ImageRef]) -> str:
    """Place each image after every other H2 starting from the second H2.

    Conservative: if there are fewer H2s than images, append leftover images
    at the bottom of the body so we still hit the image-count rubric.
    """
    if not images:
        return html
    parts = re.split(r"(<h2\b[^>]*>.*?</h2>)", html, flags=re.IGNORECASE | re.DOTALL)
    out_parts: list[str] = []
    h2_seen = 0
    img_idx = 0
    for part in parts:
        out_parts.append(part)
        if re.match(r"<h2\b", part, flags=re.IGNORECASE):
            h2_seen += 1
            # Inject after every 2nd H2, starting with the 2nd
            if h2_seen >= 2 and h2_seen % 2 == 0 and img_idx < len(images):
                out_parts.append("\n" + render_figure(images[img_idx]) + "\n")
                img_idx += 1
    # Append remaining images
    while img_idx < len(images):
        out_parts.append("\n" + render_figure(images[img_idx]) + "\n")
        img_idx += 1
    return "".join(out_parts)


def _render_faq_section(faq_items: list[FaqItem]) -> str:
    if not faq_items:
        return ""
    out = ["<h2>Frequently Asked Questions</h2>"]
    for item in faq_items:
        out.append(f"<h3>{_escape(item.question)}</h3>")
        out.append(f"<p>{item.answer}</p>")
    return "\n".join(out)


def _auto_excerpt(meta_description: str, angle: str) -> str:
    text = meta_description.strip() or angle.strip()
    return text[:200]


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


# ---------------------------------------------------------------------------
# CLI — `python -m tools.draft --help`
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    """Two operating modes:

    1. `--brief --week W --focus-kw KW`
       Print the structured prompt for one approved title. The agent feeds
       this prompt + a SERP overview to itself / Claude, generates the
       prose, and then calls back with mode 2.

    2. `--assemble --week W --focus-kw KW --prose-bundle path.json`
       Read the agent-supplied prose bundle and assemble + validate the
       draft. Bundle shape:

         {
           "body_html": "<p>...</p>",
           "faq_items": [{"question": "...", "answer": "..."}, ...],
           "images":    [{"url": "...", "alt": "...",
                          "photographer": "...", "photographer_url": "...",
                          "pexels_url": "...", "width": 1200, "height": 800}, ...],
           "seo_title": "...",
           "meta_description": "..."
         }

       Validates against the rubric (raises with the failing rule named).
       Writes the assembled draft to data/runs/_drafts/<week>.json.
    """
    import argparse

    from .images import ImageRef
    from .inventory import load as load_inventory
    from .rubric import FaqItem
    from .slate import load_slate

    parser = argparse.ArgumentParser(prog="tools.draft")
    parser.add_argument("--week", required=True)
    parser.add_argument("--focus-kw", required=True)

    sub = parser.add_mutually_exclusive_group(required=True)
    sub.add_argument("--brief", action="store_true",
                     help="Print the structured prompt for the agent to write prose")
    sub.add_argument("--assemble", action="store_true",
                     help="Read prose bundle and assemble the final draft")

    parser.add_argument("--prose-bundle",
                        help="Path to agent-supplied prose bundle JSON (with --assemble)")

    args = parser.parse_args(argv)

    slate = load_slate(args.week)
    proposal = next(
        (p for p in slate.proposals if p.focus_keyword.lower() == args.focus_kw.lower()),
        None,
    )
    if proposal is None:
        print(f"error: no proposal with focus_keyword={args.focus_kw!r} "
              f"in week {args.week}", file=__import__("sys").stderr)
        return 2

    inv = load_inventory()
    brief = prepare_brief(proposal, inv)

    if args.brief:
        print(render_brief_for_prompt(brief))
        return 0

    # --assemble path
    if not args.prose_bundle:
        print("error: --assemble requires --prose-bundle PATH",
              file=__import__("sys").stderr)
        return 2

    with Path(args.prose_bundle).open(encoding="utf-8") as fh:
        bundle = json.load(fh)

    faq_items = [
        FaqItem(question=item["question"], answer=item["answer"])
        for item in bundle.get("faq_items", [])
    ]
    images = [
        ImageRef(
            url=img["url"],
            alt=img.get("alt", brief.proposal.focus_keyword),
            photographer=img.get("photographer", "Pexels Contributor"),
            photographer_url=img.get("photographer_url", "https://www.pexels.com"),
            pexels_url=img.get("pexels_url", "https://www.pexels.com"),
            width=int(img.get("width", 0)),
            height=int(img.get("height", 0)),
        )
        for img in bundle.get("images", [])
    ]

    assembled = assemble(
        brief,
        body_html=bundle["body_html"],
        faq_items=faq_items,
        images=images,
        seo_title=bundle["seo_title"],
        meta_description=bundle["meta_description"],
    )

    # Append to data/runs/_drafts/<week>.json (one entry per call)
    drafts_path = DRAFTS_DIR / f"{args.week}.json"
    existing: dict[str, Any] = {"week": args.week, "drafts": []}
    if drafts_path.exists():
        with drafts_path.open(encoding="utf-8") as fh:
            existing = json.load(fh)
    existing["drafts"] = [
        d for d in existing.get("drafts", [])
        if d.get("slug") != assembled.slug
    ] + [
        {
            "title": assembled.title,
            "seo_title": assembled.seo_title,
            "meta_description": assembled.meta_description,
            "focus_keyword": assembled.focus_keyword,
            "slug": assembled.slug,
            "category_id": assembled.category_id,
            "audience": assembled.audience,
            "excerpt": assembled.excerpt,
            "body_html": assembled.body_html,
            "faq_items": [
                {"question": f.question, "answer": f.answer}
                for f in assembled.faq_items
            ],
            "image_alts": assembled.image_alts,
            "proposal": asdict(assembled.proposal),
        }
    ]
    drafts_path.parent.mkdir(parents=True, exist_ok=True)
    with drafts_path.open("w", encoding="utf-8") as fh:
        json.dump(existing, fh, ensure_ascii=False, indent=2)
    print(f"wrote {drafts_path}  (slug={assembled.slug}, "
          f"{len(assembled.body_html.split())} words)")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
