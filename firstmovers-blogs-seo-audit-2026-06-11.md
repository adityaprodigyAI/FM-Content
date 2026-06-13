# First Movers — Created-Blogs SEO Audit

**Run with:** `/seo-audit` (claude-seo v2.0.0 toolkit — now installed at `~/.claude/skills/seo`)
**Date:** 2026-06-11
**Scope:** The blogs the auto-poster created and that are live on firstmovers.ai (6 articles). 10 more are created and queued in the content reserve (not yet live, so not crawlable/scorable).
**Business type detected:** B2B AI consulting + education/services with a content-marketing blog (done-for-you `/consulting/` + DIY `/labs/`).
**Data sources (all keyless — no API keys used):** toolkit scripts `fetch_page.py` + `parse_html.py` (on-page, schema, content, images, links), **local headless Chromium** for lab Core Web Vitals, Google Search Console via the *existing* `mcp-gsc` connection (indexation — not a new key), live `robots.txt` + `llms.txt`.

---

## 1. Executive summary

**Aggregate SEO Health Score: 83 / 100** (all 7 weighted categories; Core Web Vitals measured in the lab via local Chromium — no Google API key required).

The content the engine produces is **strong on-page** (On-Page SEO averages 94/100). The score is held back by two structural issues that are about *distribution and markup*, not writing quality: **most articles aren't indexed yet**, and **none emit FAQ structured data** despite every one having a FAQ section.

| Category | Score | Weight |
|---|---|---|
| On-Page SEO | **94/100** | 20% |
| Content Quality | 84/100 | 23% |
| Images | 85/100 | 5% |
| Technical SEO | 80/100 | 22% |
| Performance (CWV – lab) | 90/100 | 10% |
| AI Search Readiness | 76/100 | 10% |
| Schema / Structured Data | **65/100** | 10% |

**Top 5 things to fix (priority order):**
1. **Indexation** — only 1 of 6 live articles is indexed by Google. (Critical)
2. **FAQ schema** — 0 of 6 emit FAQPage JSON-LD though all have FAQ sections. (High)
3. **Internal links into the new posts** — the indexed one has the strongest internal links; the "unknown to Google" one has none. (High)
4. **Add the new posts to `llms.txt`** — it exists but lists only older content. (Medium)
5. **One 91-char title + two below-2,500-word posts** to tidy. (Medium)

**Top 5 quick wins:**
- Request indexing + add 2–3 internal links for the 5 non-indexed posts.
- Turn on FAQPage JSON-LD in Rank Math (one settings fix benefits every post).
- Regenerate `llms.txt` so the new posts are included.
- Trim the `ai-automation-jobs` title to ≤60 chars.
- Add the flagship's striking-distance query ("ai guided shopping", pos ~20) as a sub-section.

---

## 2. Per-blog scorecard

| Article | Health | Tech | Content | On-Page | Schema | AEO | Images | Indexation |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| **ai-shopping** | **93** | 100 | 100 | 96 | 65 | 88 | 85 | ✅ Indexed |
| ai-labs | 83 | 78 | 83 | 100 | 65 | 75 | 85 | ⚠️ Discovered |
| ai-customer-support-automation | 81 | 68 | 88 | 100 | 65 | 71 | 85 | ❌ Unknown to Google |
| ai-use-cases | 80 | 78 | 75 | 95 | 65 | 75 | 85 | ⚠️ Discovered |
| ai-automation-jobs | 79 | 78 | 81 | 87 | 65 | 75 | 85 | ⚠️ Discovered |
| agentic-ai-enterprise-news | 79 | 78 | 76 | 89 | 65 | 75 | 85 | ⚠️ Discovered |

*The 14-point gap between ai-shopping (93) and the rest is almost entirely indexation: identical on-page quality, but only ai-shopping has cleared Google's index. Fix indexation + schema and the whole set moves into the low-90s.*

---

## 3. Technical SEO — 80/100

**Strong:** Every article has a correct self-referencing canonical, `index, follow` robots, HTTPS, valid Open Graph + Twitter Card meta, and is present in `post-sitemap.xml`. No accidental `noindex`, no crawl blocks (robots.txt only disallows `/wp-admin/`).

**The issue — indexation outcome (fresh GSC, 2026-06-11):**

| Article | Coverage state | Internal referrers (GSC) |
|---|---|---|
| ai-shopping | Submitted and indexed (crawled 06-11) | post-sitemap |
| ai-use-cases | Discovered – currently not indexed | `/learn-ai/` |
| ai-labs | Discovered – currently not indexed | `/ai-tools/` |
| ai-automation-jobs | Discovered – currently not indexed | post-sitemap only |
| agentic-ai-enterprise-news | Discovered – currently not indexed | post-sitemap only |
| ai-customer-support-automation | **URL unknown to Google** | none |

All are in the sitemap, so this is **not** a sitemap problem — it's crawl-budget + internal-linking. The pattern is clear: the indexed post and the "discovered" posts have internal referrers; the only post with **zero** internal links is the only one Google doesn't know exists. On a site where a few pages dominate crawl demand, new posts need internal-link signals to get crawled.

---

## 4. Content Quality — 84/100

**Strong:** Depth (2,029–3,192 words, toolkit-measured), clear author bylines (Julia McCoy / Josh McCoy in the H3 structure → E-E-A-T), on-brand voice, and outbound citations (5–20 external links per article). Heading structure is rich (12–17 H2, 6–25 H3).

**Watch:**
- `agentic-ai-enterprise-news` (2,029 words) and `ai-automation-jobs` (2,217) sit below the 2,500-word internal target.
- External-citation depth is thin on `ai-labs` (5) and `ai-customer-support-automation` (6) vs ai-shopping's 12 — more authoritative references would lift both E-E-A-T and AI-citation odds.

---

## 5. On-Page SEO — 94/100 (the strongest category)

Across all six: focus keyword in title, meta description, H1 (single H1 each), and woven through H2s; 43–45 internal links; titles and metas mostly within SERP limits. This is the engine's rubric doing its job well.

**Only real defect:** `ai-automation-jobs` has a **91-character title** ("AI Automation Jobs: Which High-Drain Roles to Reshape So Your Team Punches Above Its Weight") that will truncate in SERPs and dilute the keyword. Trim to ≤60 chars.

---

## 6. Performance (Core Web Vitals) — 90/100 (lab, keyless)

Measured by loading each blog in a **local headless Chromium** browser (no Google API key) and reading the Performance APIs:

| Article | LCP | CLS | TTFB |
|---|---|---|---|
| ai-shopping | 2,440 ms ✅ | 0.00 ✅ | 1,898 ms |
| ai-customer-support-automation | 2,168 ms ✅ | 0.006 ✅ | 1,551 ms |
| ai-use-cases | 1,924 ms ✅ | 0.005 ✅ | 1,261 ms |
| ai-labs | 1,940 ms ✅ | 0.00 ✅ | 1,261 ms |
| ai-automation-jobs | 1,876 ms ✅ | 0.00 ✅ | 1,225 ms |
| agentic-ai-enterprise-news | 1,588 ms ✅ | 0.00 ✅ | 1,352 ms |

**LCP and CLS pass on every article** (LCP ≤ 2.5 s "good", CLS ≤ 0.1 "good"). The one watch-item is **TTFB (1.2–1.9 s)** — slower than Google's 0.8 s "good" threshold, driven by the heavy WordPress/Elementor stack and server response time. LCP is currently comfortable, but slow TTFB is the first thing that degrades it under load or on a cold cache.

**Two honest caveats:** (1) these are **lab** numbers (one synthetic load on a fast connection), not real-user **field** data — for field CWV you'd need a Google API key (CrUX) or enough traffic for CrUX to report. (2) **INP** cannot be measured in the lab without simulated interaction; it's the one metric that genuinely benefits from field data.

---

## 7. Schema / Structured Data — 65/100

**Present on every article** (toolkit-detected JSON-LD): `BlogPosting`, `WebPage`, `Organization`, `WebSite`, `Person`, `ImageObject` — a solid Rank Math baseline with author/publisher entities.

**The gap:** **FAQPage JSON-LD is missing on all 6**, even though every article renders a visible "Frequently Asked Questions" section. This is why indexed `ai-shopping` shows `rich_results: null` in GSC — Google sees no FAQ markup to award a rich result. This is a single render-layer fix (Rank Math FAQ block / schema setting) that would benefit every current and future post.

---

## 8. AI Search Readiness (GEO/AEO) — 76/100

**Strong foundations:** `robots.txt` does not block AI crawlers (GPTBot/ClaudeBot/PerplexityBot are free to crawl), an `llms.txt` exists (Rank Math-generated, 29.8 KB), the content is answer-first (FAQ sections, quotable stats, definitions), and citations are present.

**Gaps:**
- `llms.txt` lists only **older** posts — none of our 6 new articles appear in it. Regenerate it so the new content is discoverable to LLMs.
- Missing FAQPage schema (see §7) also weakens AI-citation eligibility.
- 5 of 6 not indexed — AI answers disproportionately draw from indexed/known pages.

---

## 9. Images — 85/100

Each article carries 13–19 real content images (tracking pixels and inline SVGs excluded) with strong alt-text coverage and native lazy-loading. Minor upside: richer, keyword-relevant alt text on secondary images.

---

## 10. Prioritized action plan

### CRITICAL (this week)
1. **Get the 5 non-indexed posts indexed.** Add 2–3 contextual internal links from indexed/high-traffic pages (e.g. `/labs/`, `/ai-tools/`, `/learn-ai/`, the homepage hub) into each — *especially `ai-customer-support-automation`, which has zero internal links and is "unknown to Google."* Then "Request indexing" in GSC. → *Check:* coverage flips to "Indexed" within 7–14 days.

### HIGH (this sprint)
2. **Enable FAQPage JSON-LD** at the render layer (Rank Math FAQ schema). One fix, all posts. → *Check:* Google Rich Results Test detects FAQ on every live article.
3. **Strengthen internal linking** as a standing rule — every new post should ship with inbound links from 2+ relevant existing pages (fixes indexation at the source).

### MEDIUM (this month)
4. **Regenerate `llms.txt`** so the new posts are included.
5. **Trim the `ai-automation-jobs` title** to ≤60 chars; **expand** `agentic-ai-enterprise-news` and `ai-automation-jobs` past 2,500 words.
6. **Add a Google API key** to unlock CWV field data, then re-run the audit for the Performance category.

### LOW (backlog)
7. Add more authoritative external citations to `ai-labs` and `ai-customer-support-automation`.
8. Expand `ai-shopping` for its striking-distance query "ai guided shopping" (≈ position 20).
9. Improve secondary-image alt text.

---

## 11. Bottom line

The `/seo-audit` toolkit is installed and working — and it ran **fully keyless** (no Google or third-party API keys; even Core Web Vitals came from a local browser, and indexation from your existing GSC connection). It confirms the content engine is producing **genuinely strong articles** — 83/100 aggregate, 94/100 on-page, passing lab CWV, with the flagship indexed post scoring 93. The ceiling on every score is the same two plumbing fixes: **force indexation through internal links** and **turn on FAQ schema**. Neither requires rewriting a word — and both would lift the whole portfolio into the low-90s.

*Generated with the claude-seo `/seo-audit` skill (keyless), local Chromium for CWV, and Google Search Console. Per-page data: `.tmp/seo_audit/`.*
