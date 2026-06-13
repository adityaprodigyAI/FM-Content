# First Movers — Auto-Poster Blog SEO Report

**Date:** 2026-06-09
**Scope:** Every blog post created by the FM-Content VPS auto-poster pipeline (2026-05-08 → 2026-06-02)
**Analysis framework:** `claude-seo` v2.0.0 universal SEO skill (technical, E-E-A-T, schema, GEO/AEO, indexation, links) applied to First Movers' live data sources (Google Search Console, public page HTML, the published-content inventory snapshot)
**Property:** `sc-domain:firstmovers.ai` (GSC, siteOwner access)

---

## 1. Executive summary

The auto-poster is producing **technically strong on-page content** — but almost none of it is reaching Google, and most of it never even gets published. The pipeline's *writing* is working; the **publish → index → rank funnel is broken downstream of draft creation.**

### The funnel (this is the headline)

| Stage | Count | % of created |
|---|---:|---:|
| Posts **created** & pushed to WordPress | **16** | 100% |
| Posts **published** (live, HTTP 200) | **6** | 38% |
| Published posts **indexed** by Google | **1** | 6% |
| Indexed posts with **any clicks** (90d) | **0** | 0% |
| Indexed posts with **FAQ rich results** | **0** | 0% |

**Portfolio SEO Health Score: 24 / 100.**
Live posts average **63/100 on-page** but are dragged to a portfolio score of 24 because 10 of 16 are unpublished and only 1 of 6 published is indexed. *The content quality is real; the distribution is the failure.*

### Four things to fix, in order

1. **CRITICAL — Publish the backlog.** 10 of 16 created posts are sitting as WordPress drafts (including 3 duplicate-topic re-pushes). They have zero SEO value until Nikki publishes them. This is the single largest ROI leak.
2. **CRITICAL — Fix indexation.** Of 6 published posts, only `ai-shopping` is indexed. The other 5 are "Discovered – currently not indexed" or "URL unknown to Google" despite being in the sitemap. This is a crawl-budget + internal-linking problem.
3. **HIGH — FAQ schema is missing on 100% of live posts.** Every post renders a visible "Frequently Asked Questions" section, but **none emit FAQPage JSON-LD.** This violates FM hard rule #7 and forfeits FAQ rich results and AI-Overview citation eligibility.
4. **HIGH — Self-cannibalization.** The pipeline proposed the same focus keyword on multiple days (`ai-automation` ×2, `ai-use-cases` ×2, `ai-customer-experience` ×2) and targets keywords where First Movers already ranks with pillar pages (`/labs/`, `/blueprint/`, `/what-is-ai-automation/`).

---

## 2. Methodology & data provenance

This report follows the `claude-seo` synthesis flow (PERCEIVE → ANALYZE → VALIDATE → ACT) and buckets findings into Critical / High / Medium / Low with a falsifiable check per recommendation.

**Data sources used (all WAF-independent):**

| Source | What it gave us | Access path |
|---|---|---|
| Google Search Console | Indexation status, impressions/clicks/position, sitemap inclusion | Local `mcp-gsc` OAuth (siteOwner) |
| Live page HTML | Title, meta, headings, word count, schema, links, images, focus-keyword placement | Public `curl` + browser UA (Cloudflare allows public pages) |
| Published-content inventory | Cross-reference of published posts, focus keywords | `data/inventory/firstmovers-ai.json` (snapshot 2026-06-01) |
| Local pipeline records | Canonical list of what the auto-poster pushed (post IDs, dates, slugs) | `data/runs/_daily/*.json` |

**Data sources that were unavailable this session (noted for transparency):**

| Source | Status | Impact on report |
|---|---|---|
| WordPress REST `/wp-json` | **403 — Cloudflare/WAF blocked** from this IP (both MCP connector and direct REST) | Could not pull draft bodies or live post meta directly; used GSC + public HTML + local records instead. The documented browser-UA REST workaround now also fails from non-VPS IPs. |
| GA4 (`tools/ga4.py`) | **503 — ADC token expired** ("Reauthentication is needed. Run `gcloud auth application-default login`") | No engagement/session metrics. GSC covers search performance, which is the more decisive SEO signal. |
| Ahrefs (connector) | **API units exhausted** (0 remaining) | No keyword volume/difficulty or domain-rating enrichment. Competition/cannibalization assessed via GSC ranking data for existing pillars instead. |

> **Action for next run:** refresh GA4 ADC (`gcloud auth application-default login`) and confirm Ahrefs unit quota before re-running, to add engagement metrics and keyword-opportunity scoring. None of these gaps change the headline findings — indexation and publication are the binding constraints.

---

## 3. What the auto-poster created (canonical list)

16 posts pushed to WordPress between 2026-05-08 and 2026-06-02 (author = Josh McCoy, WP user 3):

| Date | WP ID | Pushed slug | Live URL | Status |
|---|---:|---|---|---|
| 2026-05-08 | 72606 | ai-shopping | `/ai-shopping/` | ✅ **Live + indexed** |
| 2026-05-12 | 72659 | ai-sales-email-automation | — | ⬜ Draft |
| 2026-05-13 | 72667 | ai-customer-experience | — | ⬜ Draft |
| 2026-05-15 | 72710 | ai-customer-support-automation | `/ai-customer-support-automation/` | 🟡 Live, **unknown to Google** |
| 2026-05-16 | 72674 | ai-use-cases | `/ai-use-cases/` | 🟡 Live, discovered–not indexed |
| 2026-05-20 | 73547 | ai-customer-experience | — | ⬜ Draft (**duplicate topic**) |
| 2026-05-21 | 73548 | labs-explained | `/ai-labs/` (slug drifted) | 🟡 Live, discovered–not indexed |
| 2026-05-23 | 73549 | ai-use-cases | — | ⬜ Draft (**duplicate topic**) |
| 2026-05-24 | 73550 | blueprint-explained | — | ⬜ Draft |
| 2026-05-25 | 73670 | ai-automation | `/ai-automation-jobs/` (slug drifted) | 🟡 Live, discovered–not indexed |
| 2026-05-26 | 73671 | is-ai-taking-over-jobs | — | ⬜ Draft |
| 2026-05-27 | 73672 | ai-automation | — | ⬜ Draft (**duplicate topic**) |
| 2026-05-28 | 73674 | ai-workflows | — | ⬜ Draft |
| 2026-05-29 | 73677 | agentic-ai-enterprise-news | `/agentic-ai-enterprise-news/` | 🟡 Live, discovered–not indexed |
| 2026-05-30 | 73678 | ai-driven-marketing-campaigns | — | ⬜ Draft |
| 2026-06-02 | 74166 | ai-replacing-jobs | — | ⬜ Draft |

*(Liveness verified by HTTP status on 2026-06-09; indexation by GSC URL Inspection.)*

---

## 4. Critical findings

### C1 — 62% of created content is stranded in drafts
10 of 16 posts (IDs 72659, 72667, 73547, 73549, 73550, 73671, 73672, 73674, 73678, 74166) are unpublished WordPress drafts. By design the pipeline pushes `status=draft` and only Nikki publishes — but the publishing step is not keeping pace with creation. **These posts have zero SEO footprint: no URL, no index entry, no traffic, no rank.** The pipeline's daily cost is being incurred without the payoff.
**Falsifiable check:** `curl -I` each draft slug → currently 404; after publish → 200.

### C2 — Only 1 of 6 published posts is indexed
GSC URL Inspection (2026-06-09):

| Live URL | Coverage state | Indexed? | Internal referrers |
|---|---|:--:|---|
| `/ai-shopping/` | Submitted and indexed | ✅ | post-sitemap |
| `/ai-use-cases/` | Discovered – currently not indexed | ❌ | `/learn-ai/` |
| `/ai-labs/` | Discovered – currently not indexed | ❌ | `/ai-tools/` |
| `/agentic-ai-enterprise-news/` | Discovered – currently not indexed | ❌ | post-sitemap only |
| `/ai-automation-jobs/` | Discovered – currently not indexed | ❌ | post-sitemap only |
| `/ai-customer-support-automation/` | **URL unknown to Google** | ❌ | none |

All six are present in `post-sitemap.xml`, so this is **not** a sitemap problem. The pattern correlates with **internal linking**: the only indexed post has the strongest internal-link signal; the "unknown to Google" post has none. Root cause is crawl-budget allocation on a site where a handful of pages (e.g., `/bible-ai-analysis/` at 134K impressions) dominate crawl demand, combined with thin internal links into the new posts.
**Falsifiable check:** add 2–3 internal links from indexed/high-authority pages into each non-indexed post, request indexing in GSC, re-inspect in 7–14 days → coverage flips to "Indexed."

### C3 — Zero organic clicks across the entire created portfolio
Over the trailing 90 days (2026-03-11 → 2026-06-09), the only created post with any GSC footprint is `/ai-shopping/`: **5 impressions, 0 clicks** (queries "ai guided shopping" pos 20, "ai shopping guide" pos 57). Every other live post returns "No search data." The portfolio has generated **0 organic clicks** to date. This is expected for content this new *and* not indexed — but it confirms C1/C2 are the binding constraints, not content quality.

---

## 5. High-priority findings

### H1 — FAQPage schema missing on 100% of live posts
Every live post renders a visible "Frequently Asked Questions" H2 section, yet **none emit FAQPage JSON-LD** (verified: 0 `FAQPage` and 0 `"Question"` occurrences in raw HTML across all 6). The pages do emit Rank Math's defaults (`BlogPosting`, `WebPage`, `Organization`, `Person`, `WebSite`, `ImageObject`), but the FAQ structured data the rubric mandates (FM hard rule #7) is absent at render time. This is why indexed `/ai-shopping/` shows `rich_results: null`.
**Impact:** forfeits FAQ rich-result eligibility and weakens AI-Overview/AEO citation odds — exactly the GEO surface First Movers cares about.
**Falsifiable check:** validate any live post in Google's Rich Results Test → currently "No items detected for FAQ"; after fix → FAQ detected.

### H2 — Self-cannibalization (internal + against existing pillars)
**Internal duplication:** the daily-idea generator proposed the same focus keyword on multiple days — `ai-automation` (05-25 & 05-27), `ai-use-cases` (05-16 & 05-23), `ai-customer-experience` (05-13 & 05-20). Each second push is now a stranded draft, but the repetition indicates the discovery layer isn't deduping against its own recent proposals.
**Against existing ranking pages (from GSC, 90d):**

| New post targets | Existing FM page already ranking | Existing position | Risk |
|---|---|---|---|
| `ai-labs` / "labs explained" | `/labs/` | **4.4** (956 clicks) | High — competing with a top-5 pillar |
| `blueprint-explained` (draft) | `/blueprint/` | 8.2 | Medium |
| `ai-automation-jobs` | `/what-is-ai-automation/` (pos 58.6), `/ai-automation-workflows/` (pos 29.9) | weak | Low–Medium (opportunity to consolidate) |

**Falsifiable check:** run the cannibalization gate (`tools/cannibalization.py`) against a *fresh* inventory snapshot for each draft's focus keyword before publishing.

### H3 — Title-length and em-dash hygiene slips
- `/ai-automation-jobs/` title is **91 characters** ("AI Automation Jobs: Which High-Drain Roles to Reshape So Your Team Punches Above Its Weight") — will truncate in SERPs (~60 char limit) and dilutes the focus keyword.
- **Em dashes in body** on `/agentic-ai-enterprise-news/` and `/ai-automation-jobs/`, violating FM hard rule #4 (hyphens only — Josh April 2026 directive).
**Falsifiable check:** title ≤ 60 chars; `grep "—"` over rendered body returns 0.

### H4 — Slug drift between push and publish
Two posts publish under slugs different from what the pipeline pushed: `labs-explained → /ai-labs/`, `ai-automation → /ai-automation-jobs/` (the `/ai-automation/` alias still resolves 200 but canonicalizes to `/ai-automation-jobs/`). The pipeline's local `wp_post_id`/slug records therefore drift from reality, which is why reconciliation against live data was necessary. Not an SEO defect per se, but it breaks the pipeline's own tracking and any internal-link automation keyed on the pushed slug.

---

## 6. Medium / Low findings

- **M1 — Two live posts below the 2,500-word floor** (FM hard rule #8): `/agentic-ai-enterprise-news/` (~2,029 words) and `/ai-automation-jobs/` (~2,217 words). (Counts are from stripped article text and may differ slightly from the rubric's tokenizer; treat as "verify against rubric.")
- **M2 — External-link depth varies:** `/ai-labs/` has only 5 external dofollow links and `/ai-customer-support-automation/` has 6 — fine vs the ≥3 rule, but thin vs `ai-shopping`'s 12. More authoritative citations strengthen E-E-A-T and GEO.
- **M3 — Image alt focus-keyword coverage is partial** (3–7 of ~15–19 images carry the focus keyword in alt). The hero-alt auto-injection is working; secondary images could carry more descriptive, keyword-relevant alts.
- **L1 — Canonical/robots are correct everywhere** (`index, follow`, self-canonical) — no accidental noindex. Good.
- **L2 — On-page focus-keyword placement is excellent** across all 6 (keyword in title, meta, H1, and first 100 words in every case). The rubric is clearly enforcing this well.

---

## 7. Per-post scorecards (live posts)

Scoring: on-page technical /25 · links /15 · schema /20 · images /10 · indexation+performance /30. Indexation gates the score — strong on-page work caps out around 60 until the page is indexed.

| Post | Score | Words | H2 | Schema | Internal / External links | Indexation |
|---|:--:|--:|--:|---|---|---|
| **`/ai-shopping/`** | **80/100** | 3,177 | 17 | BlogPosting (no FAQ) | 45 / 12 | ✅ Indexed |
| `/ai-use-cases/` | 62/100 | 2,411 | 16 | BlogPosting (no FAQ) | 44 / 7 | Discovered–not indexed |
| `/ai-labs/` | 62/100 | 2,576 | 12 | BlogPosting (no FAQ) | 44 / 5 | Discovered–not indexed |
| `/ai-customer-support-automation/` | 60/100 | 2,770 | 17 | BlogPosting (no FAQ) | 43 / 6 | Unknown to Google |
| `/agentic-ai-enterprise-news/` | 57/100 | 2,029 | 14 | BlogPosting (no FAQ) | 44 / 20 | Discovered–not indexed |
| `/ai-automation-jobs/` | 55/100 | 2,217 | 16 | BlogPosting (no FAQ) | 44 / 20 | Discovered–not indexed |

**Read:** every live post scores 55–62 on-page-and-structure except `ai-shopping`, which clears 80 purely because it's indexed. The recurring −12 across all six is the missing FAQPage schema; the recurring indexation penalty is the −18 to −28 gate. **Fix schema + indexation and every one of these jumps into the 80s.**

### Highlights per post
- **`/ai-shopping/`** — the model post. 3,177 words, 17 H2s, 1.35% keyword density, 13/16 images with alt, indexed. Only gaps: FAQ schema, and it's earning impressions for "ai guided shopping" (pos 20) — a striking-distance query worth a section expansion.
- **`/ai-use-cases/`** — strong (2,411 words, internal link from `/learn-ai/`). Needs an indexing nudge + FAQ schema.
- **`/ai-labs/`** — directly competes with the `/labs/` pillar ranking at position 4.4. Decide: consolidate into `/labs/` or differentiate intent (the post is informational/DFY; `/labs/` is the product page). Do not let both chase "ai labs."
- **`/ai-customer-support-automation/`** — highest content depth signal (2,770 words, 25 H3s) but **completely invisible to Google** (no internal links at all). Highest-leverage indexation fix: link to it from a relevant indexed page.
- **`/agentic-ai-enterprise-news/`** & **`/ai-automation-jobs/`** — both below word-count floor, both carry em dashes, `ai-automation-jobs` has a 91-char title. Clean these before pushing for indexation.

---

## 8. Draft inventory (10 unpublished posts)

These have no live SEO footprint. They cannot be analyzed for indexation/performance and (because `/wp-json` is WAF-blocked) their bodies could not be pulled this session. From the pipeline proposal records:

| WP ID | Intended focus keyword | Audience | Note |
|---:|---|---|---|
| 72659 | ai sales email automation | — | Oldest stranded draft (05-12) |
| 72667 | ai customer experience | — | First of a duplicate pair |
| 73547 | ai customer experience | — | Duplicate topic |
| 73549 | ai use cases | — | Duplicate of live `/ai-use-cases/` |
| 73550 | blueprint explained | DFY | Cannibalizes `/blueprint/` pillar |
| 73671 | is ai taking over jobs | — | — |
| 73672 | ai automation | — | Duplicate of live `/ai-automation-jobs/` |
| 73674 | ai workflows | — | — |
| 73678 | ai driven marketing campaigns | — | — |
| 74166 | ai replacing jobs | — | Newest stranded draft (06-02) |

**Recommendation:** triage before publishing. Publish the unique, non-cannibalizing drafts (ai-sales-email-automation, is-ai-taking-over-jobs, ai-workflows, ai-driven-marketing-campaigns, ai-replacing-jobs). **Delete or merge** the 3 duplicate-topic drafts and re-evaluate the two that cannibalize pillars (ai-customer-experience, blueprint-explained).

---

## 9. Prioritized action plan

Dependency-sequenced. Each item has an owner-agnostic, falsifiable success check.

### CRITICAL (do this week)
1. **Get `/ai-customer-support-automation/` and the 4 discovered posts indexed.**
   - Add 2–3 contextual internal links from indexed/high-traffic pages (e.g., `/ai-tools/`, `/labs/`, the homepage hub) into each non-indexed post.
   - Submit each via GSC "Request indexing."
   - ✅ *Check:* coverage state flips to "Indexed" within 14 days.
2. **Triage + publish the draft backlog.** Publish the 5 unique drafts; delete/merge the 3 duplicates; decide on the 2 cannibalizing drafts.
   - ✅ *Check:* draft count drops from 10 to ≤4; each published slug returns 200.

### HIGH (this sprint)
3. **Restore FAQPage JSON-LD at render time.** Investigate why the rubric's FAQ schema isn't reaching the published page (Rank Math stripping it, or the assembler not injecting it). This is a pipeline/render fix that benefits every future post.
   - ✅ *Check:* Rich Results Test detects FAQ on all live posts.
4. **Resolve the `/ai-labs/` vs `/labs/` cannibalization.** Consolidate or hard-differentiate intent; set the canonical/internal-link strategy so they don't compete.
   - ✅ *Check:* only one URL targets "ai labs" / "labs" head terms.
5. **Add a same-keyword dedupe to the daily-idea discovery layer** so it stops re-proposing `ai-automation`/`ai-use-cases`/`ai-customer-experience`.
   - ✅ *Check:* no focus keyword repeats within a rolling 30-day window of proposals.

### MEDIUM
6. **Fix the two below-floor posts and the 91-char title; strip em dashes** on the two offending live posts (hard rules #4, #8).
7. **Reconcile pipeline slug tracking with live slugs** (handle publish-time slug drift) so internal-link automation and `wp_post_id` records stay accurate.
8. **Expand `/ai-shopping/` for its striking-distance query** "ai guided shopping" (pos 20) — add a focused section; it's the one post with live impressions to build on.

### LOW
9. Increase external dofollow citation depth on `/ai-labs/` and `/ai-customer-support-automation/`.
10. Improve secondary-image alt text to carry descriptive, keyword-relevant phrasing.

---

## 10. Bottom line

The auto-poster writes genuinely good blog posts — 2,000–3,200 words, clean heading structure, disciplined focus-keyword placement, strong internal linking, correct canonical/robots. The `claude-seo` audit confirms the *content* layer is healthy (live posts average 63/100 on-page, and the one indexed post scores 80).

But **content that isn't published, indexed, and structured-data-marked produces no SEO outcome.** Today the system converts 16 created posts into 1 indexed page and 0 organic clicks. Fixing three plumbing problems — publish the backlog, force indexation via internal links, and restore FAQ schema — would convert most of the existing 63/100 on-page work into 80/100 live, indexed, rich-result-eligible pages without writing a single new word.

---

### Appendix — raw evidence
- On-page extraction: `.tmp/seo_report/onpage_analysis.json`
- Scored master dataset: `.tmp/seo_report/master_summary.json`
- Live HTML snapshots: `.tmp/seo_report/html/*.html`
- GSC URL Inspection + page-query pulls: run 2026-06-09 against `sc-domain:firstmovers.ai`
- Pipeline push records: `data/runs/_daily/*.json`; inventory: `data/inventory/firstmovers-ai.json`
