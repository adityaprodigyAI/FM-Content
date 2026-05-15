---
name: fm-prose-generation
description: Use when generating the body of a firstmovers.ai blog draft. This is the method skill (HOW to write); pair with firstmovers-blog-rubric (WHAT to hit). Covers the 5-step prose workflow, section pacing, citation density, internal/external link weaving, and the retry-on-RubricViolation loop.
verified: 2026-05-12
---

# Prose generation method

This skill is paired with `firstmovers-blog-rubric`:
- **`firstmovers-blog-rubric`** = the target (Rank Math 19-check rubric, profile stats, allowlists, audience routing)
- **`fm-prose-generation`** = the method (how to actually write a body that hits the target)

## The 5-step workflow

### 1. Load the rubric

    Skill(skill="firstmovers-blog-rubric")

That gives you power words, internal/external link allowlists, audience routing rules, and the don'ts list.

### 2. Fetch SERP context

    serp = mcp__ahrefs__serp-overview(
        keyword=focus_keyword,
        country="us",
        top_positions=10,
        select="title,url,position,domain_rating,backlinks,traffic,top_keyword",
    )

Read the top-10 titles and meta descriptions. This is what you must out-write. Identify:
- Which angles everyone is taking (skip those)
- Which angle is missing (lead with that)
- What domain authority you're up against (DR60+ means you need stronger citations than them)

### 3. Draft

Outline first, then prose. Target:
- **≥ 2,500 words, target 3,500** (rubric §1)
- **≥ 6 H2 sections, target 7** (median of published posts is 7)
- **At least 1 H2 contains the focus keyword**
- **Lede mentions focus keyword in first paragraph**
- **Paragraphs < 120 words each** (Rank Math grades this)
- **≥ 3 external dofollow citations** from `external_links.curated_for(category_id)` (target 6+)
- **One audience-routed CTA** at the end (rubric §9 has the canonical mapping)
- **3 internal "read next" links** at the bottom, audience-matched

### Section pacing template

| Section | Purpose | Words |
|---|---|---|
| Lede (no H2) | Mention focus keyword, set stakes, promise the answer | 60-120 |
| H2 #1 — Frame the problem | Why this matters now (cite a recent stat) | 350-500 |
| H2 #2 — Definitions / context | The thing the AI search assistants will quote | 350-500 |
| H2 #3 — Core argument (focus kw in heading) | Your differentiated take | 500-700 |
| H2 #4 — Evidence / case studies | 2-3 concrete examples with stats | 400-600 |
| H2 #5 — How to do it / framework | Numbered or bulleted, operator-grade | 400-600 |
| H2 #6 — Common mistakes / objections | What competitors miss | 300-500 |
| H2 #7 — What to do next | Actionable summary (NOT the CTA itself) | 200-300 |
| FAQ | 3-7 question/answer pairs, AEO-friendly | varies |
| CTA block | Audience-routed (per rubric §9) | 60-100 |
| Read next aside | 3 internal links | 30 |

### 4. Citation density

Target: **one external citation per 300-400 words.** A 3,500-word post should have ~10 citations. The published median is 11. Spread them across H2s — not all in one section. Source list is in `firstmovers-blog-rubric` §8.

### 5. Validate + retry

    try:
        assembled = assemble(brief, body_html=body, faq_items=faqs, seo_title=seo, meta_description=meta)
    except RubricViolation as e:
        # e.message names the exact rule violated
        # regenerate the prose addressing the named rule; retry up to 2 times
        ...

The retry loop is capped at 2 because if the model can't get it right in 3 tries, something structural is wrong (focus keyword too narrow, SERP dominated by DR we can't match, OR `external_links.curated_for` returned empty for that category).

## Internal link weaving

`internal_links.select(audience, exclude_url, max_total=5)` picks 5 audience-relevant internal links. Weave them into the body naturally, not in a bibliography at the end. Anchored on the relevant phrase. Never `utm_source=internal` (nukes GA4 attribution per rubric §11).

## What "good prose" looks like (style guide)

- **Sentence length variance.** Mix 6-word sentences with 25-word sentences. Pure long sentences scan as AI; pure short sentences scan as bullet-point summary.
- **Concrete over abstract.** "McKinsey's 2024 generative-AI survey found 65% of orgs report regular use, up from 33% the year prior" beats "AI adoption is growing."
- **No em dashes.** Hyphens only. (Josh April 2026 directive.)
- **No "free audit".** Anywhere. Consulting is $25-60K.
- **No marketing voice.** First Movers is a B2B consulting firm; prose should read like a senior consultant writing, not a content marketer.
- **Operator-grade specifics.** When listing steps or frameworks, the steps must be doable. Avoid "leverage AI" / "drive value" — name the tool, name the metric.

## Don't

- Don't generate `<h1>` in the body (WP renders the title as page H1).
- Don't generate BlogPosting or BreadcrumbList JSON-LD (Rank Math emits those).
- Don't emit `[AFFILIATE_LINK:TOOLNAME]` tokens — no resolver in pipeline.
- Don't include images in the body (v1 ships text-only per rubric §6).
- Don't trail the post title with a period.

## See also

- `firstmovers-blog-rubric` — the target this method aims at
- `fm-ahrefs` — for the `serp-overview` call in step 2
- `fm-wordpress-push` — the next step after `assemble` returns clean
