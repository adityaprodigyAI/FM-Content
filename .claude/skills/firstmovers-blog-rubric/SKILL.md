---
name: firstmovers-blog-rubric
description: Use when writing or auditing a blog post for firstmovers.ai. Captures the Rank Math 19-check rubric, the First Movers published-post profile, curated power words, internal/external link allowlists, image attribution patterns, and the assembler's hard-fail validations. Reference before generating any draft prose.
---

# First Movers Blog Rubric

Canonical reference for writing or auditing any blog post on firstmovers.ai. Synthesizes the Rank Math grading rubric, the published-post profile (15 most recent published posts, 2026-04-29 sample), and the validators baked into `tools/rubric.py`.

> **v1 ships text-only drafts.** No images. Nikki adds a featured image post-publish if she wants one. To re-enable image requirements, see the bottom of section 6.

> **Outcome target:** every draft scores ≥75/100 in Rank Math on first review (without images, the ceiling drops slightly — Rank Math grades the "Use of Media" check at 0/4 when the body has no images, but the rest of the rubric still earns 75-85).

---

## 1. Outcome target

| Dimension | Hard floor | Production target |
|---|---|---|
| Word count | 2,000 | **2,500** |
| H2 sections | 6 | **7** |
| Images (`<img>` tags) | **0 (disabled in v1)** | 0 |
| Internal links (in body, excluding CTA) | 4 | **6+** |
| External dofollow links | 3 | **6+** |
| SEO title length | ≤ 60 chars | 50-58 chars |
| Post title length | ≤ 120 chars | 60-90 chars |
| Meta description length | ≤ 155 chars | 130-150 chars |
| Focus keyword in: SEO title, meta desc, URL, first 10% of content, ≥1 H2 | all required | all required |

Defaults are calibrated to the **p25** of published First Movers posts. Targets are calibrated to the **median**.

---

## 2. Rank Math rubric (every check)

[Source: rankmath.com/kb/score-100-in-tests/](https://rankmath.com/kb/score-100-in-tests/)

### Basic SEO (largest weight)
| Check | Satisfied by | Meta key |
|---|---|---|
| Focus keyword in SEO Title | `seo_title` includes focus keyword (lead with it) | `rank_math_title` |
| Focus keyword in Meta Description | `meta_description` includes focus keyword | `rank_math_description` |
| Focus keyword in URL | slug includes focus keyword | post slug |
| Focus keyword at beginning of content | first paragraph mentions focus keyword | post content |
| Focus keyword in content (density 1-1.5%) | natural recurring use (~10× across body) | post content |
| Content length (≥600w pass, 2500w = 100%) | body ≥ 2,000 words; aim 2,500 | post content |

### Additional SEO
| Check | Satisfied by | Notes |
|---|---|---|
| Focus keyword in subheadings | ≥1 H2 contains focus keyword | hard-fail validator |
| Focus keyword in image alt | n/a in v1 (text-only) | re-enable when images turn on |
| Linking to External Sources | ≥3 outbound dofollow links | hard-fail validator |
| Linking to Internal Resources | auto-injected via `internal_links.select` | always passes |
| Focus Keyword Uniqueness | cannibalization gate blocks reuse | always passes |
| Content AI | paid Rank Math add-on — **skip** | won't subscribe |

### Title readability
| Check | Satisfied by |
|---|---|
| Focus keyword at start of SEO Title | put focus keyword first in `seo_title` |
| Power word in title | hard-fail validator — at least one word from `POWER_WORDS` |
| Number in title | include a year ("2026") or count ("5 wins", "3 tiers") |

---

## 3. First Movers blog profile (calibration data 2026-04-29)

Stats across 15 most recent published blogs:

| Metric | min | p25 | **median** | p75 | max |
|---|---|---|---|---|---|
| Words | 1,591 | 2,048 | **2,276** | 2,694 | 3,406 |
| H2 sections | 0 | 6 | **7** | 9 | 9 |
| Images | 2 | 3 | **4** | 6 | 7 |
| Internal links | 4 | 5 | **6** | 8 | 13 |
| External links | 1 | 8 | **11** | 16 | 29 |

---

## 4. Title rules

### Post title (`title`)
- Up to 120 chars. The human-facing H1 — can be long if it sets clear context.
- No trailing period.

### SEO title (`seo_title`, `rank_math_title`)
- ≤ 60 chars. Truncated in SERP after that.
- **Must contain a power word from POWER_WORDS** (hard-fail validator):

```
Credibility:   proven, definitive, essential, complete, comprehensive,
               ultimate, official, authoritative, reliable, trusted
Practical:     practical, actionable, effective, powerful, smart,
               strategic, rigorous, tested, field-tested, battle-tested
Discovery:     surprising, shocking, hidden, secret, untold, insider,
               revealed, exposed, uncovered, breakthrough, remarkable
Speed:         fast, instant, quick, rapid, lightning
Quality:       best, top, elite, premier, leading, killer, brilliant,
               stunning, incredible, amazing, genius, unbeatable,
               unstoppable, bulletproof, foolproof, ironclad
Value:         free, cheap, affordable, lucrative, valuable
Ease:          easy, simple, effortless, seamless, painless
Honesty:       honest, real, true, raw, no-nonsense
```

- Pattern: `<Focus Keyword>: <Power Word> <Number/Year> <Noun>`
- Acronyms stay uppercase: AI, ROI, CRM, SaaS, API, KPI, RPA, LLM, MCP.

---

## 5. Body structure

1. **Opening lede** — first paragraph mentions the focus keyword. 2-4 sentences.
2. **6-9 H2 sections** (target 7). At least one H2 must contain the focus keyword.
3. **H3 sub-points** under H2s where useful.
4. **Short paragraphs** — Rank Math grades sub-120-word paragraphs.
5. **CTA** — one audience-routed CTA block at the bottom.
6. **Read next aside** — 3 internal links to audience-relevant posts.
7. **FAQPage JSON-LD** — auto-appended. **Do not** emit BlogPosting or BreadcrumbList JSON-LD.

---

## 6. Image rules — DISABLED IN V1

v1 ships text-only drafts. The Pexels integration code is preserved (in `tools/images.py`) but the validator is inert and `tools/draft.py::assemble` accepts no images.

When you're ready to turn images back on:
1. Set `MIN_IMAGE_COUNT >= 3` in `tools/rubric.py`
2. Re-add `_validate_images` to `_VALIDATORS` in `tools/rubric.py`
3. Pass `images=[...]` into `draft.assemble`
4. Set `PEXELS_API_KEY` in `.env` and the GH Actions secret store
5. The agent fetches via `images.fetch_pexels(focus_keyword, count=4)` and passes the result to `assemble`

Pexels CDN is hotlinked (Cloudways/Wordfence blocks WP media uploads). Every `<figcaption>` carries the photographer credit per Pexels API license.

---

## 7. Internal links

Auto-injected via `internal_links.select(audience, exclude_url, max_total=5)`.

### Audience routing
- **`done-for-you`** posts → /consulting/, Tier-1 done-for-you pages, done-for-you blog cross-links.
- **`diy`** posts → /labs/, DIY blog cross-links.

Aim for **6+ internal links total** in the rendered post.

---

## 8. External citations

≥ 3 from `external_links.curated_for(category_id)` (target 6+, median of published posts is ~11).

### Curated allowlist hosts
- HBR, McKinsey, BCG, Bain, Deloitte, Gartner
- Stanford HAI, MIT Sloan, MIT Tech Review
- WEF, OECD
- Anthropic, OpenAI, Google DeepMind
- Salesforce, HubSpot, CMI (state-of reports only)
- The Verge

### Excluded competitors
**Don't cite or link to:** PwC, Accenture, Capgemini, IBM, doneforyou.com, automationagency.com, ugenticai.com.

### Where to weave citations
- Back load-bearing claims with stats — link inline, not in a bibliography.

---

## 9. CTA framework

| Audience | CTA destination | Button text |
|---|---|---|
| `done-for-you` | `/consulting/` | "Schedule a Free Strategy Call" |
| `diy` | `/labs/` | "Explore AI Labs" |

**Forbidden phrases** (case-insensitive, hard-fail validator): `free audit`. Consulting is $25-60K — implying free misrepresents the offer.

---

## 10. Schema

Emit **FAQPage JSON-LD only**. Rank Math auto-emits BlogPosting + BreadcrumbList.

Required: 5-7 `mainEntity` Question/Answer pairs phrased as the user (or AI search engine) would query them.

---

## 11. Don'ts

- **No leading `<h1>` in body.** WP renders the title as page H1.
- **No `[AFFILIATE_LINK:TOOLNAME]` placeholders.** No token resolver in the pipeline.
- **No blank Rank Math meta.** Validators reject blank `seo_title`, `meta_description`, `focus_keyword`.
- **No SEO titles >60 chars.**
- **No `utm_source=internal` on internal links.** Nukes GA4 attribution.
- **No competitor citations** (PwC, Accenture, Capgemini, IBM).
- **No `status="publish"` on auto-generated posts.** Always `status="draft"`.
- **No em dashes anywhere** (Josh April 2026 directive — hyphens only).
- **No trailing period in titles.**

---

## 12. Quick-reference checklist (before assembly)

```
[ ] focus keyword in first paragraph (lede)
[ ] focus keyword in URL slug
[ ] focus keyword in meta_description (≤155 chars)
[ ] seo_title ≤ 60 chars, contains focus keyword + power word + number
[ ] post title ≤ 120 chars, no trailing period, no em dash
[ ] body ≥ 2,500 words
[ ] ≥ 6 H2 sections, at least one contains focus keyword
[ ] paragraphs <120 words each
[ ] FAQPage JSON-LD with 3-7 Q&A pairs
[ ] ≥ 3 external dofollow links from external_links.curated_for(category_id)
[ ] no [AFFILIATE_LINK:X] tokens
[ ] no leading <h1> in body
[ ] no manual BlogPosting or BreadcrumbList JSON-LD
[ ] CTA matches audience (done-for-you → /consulting/, diy → /labs/)
[ ] no "free audit" anywhere
[ ] no em dashes
[ ] no images (v1 ships text-only)
```
