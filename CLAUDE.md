# FM-Content — Operating Instructions

You are operating the **weekly content automation pipeline for FirstMovers.ai**. Your job is to deliver 7 high-quality WordPress blog drafts every Wednesday for Nikki to review and publish across the week.

## The single most important rule

**Never propose a topic that overlaps a topic FirstMovers.ai has already published.** That was the v5 bug we rebuilt this pipeline to fix. The cannibalization gate (`tools/cannibalization.py`) is the structural defense — never weaken it, never bypass it, never run a draft on a stale or degraded inventory snapshot.

## The flow

| Day (Phoenix UTC-7) | Job | What happens |
|---|---|---|
| Sunday 07:00 | `python -m tools.slate --week=NNNN-WNN --emit` | Refresh inventory → run 4 discovery sources → cannibalization gate → top 12 → ClickUp parent task with 12 subtasks for Nikki |
| Sun-Tue | (Nikki) | Tick ≤7 subtasks to "done" |
| Wednesday 09:00 | `python -m tools.draft --week=NNNN-WNN --push` | Read approvals → re-run cannibalization → SERP fetch + Claude prose + rubric validate + Pexels images → push to WP as `status=draft` |
| Wed-Sun | (Nikki) | Polish drafts in WP, get Josh CTA approval, publish |

Phoenix is fixed offset UTC-7 year-round. No DST.

## Hard rules (enforced in code)

1. `status=draft` on creation. Only Nikki publishes.
2. Author = Josh McCoy (WordPress user 3). Single source of truth in `tools/identities.py`.
3. No "free audit" anywhere — body, CTA, newsletter, social.
4. No em dashes anywhere (hyphens only — Josh April 2026 directive).
5. No trailing period in titles.
6. Audience routing: `done-for-you` → `/consulting/`; `diy` → `/labs/`. Never crossed.
7. FAQPage JSON-LD only. Rank Math emits BlogPosting + BreadcrumbList at render time.
8. Word count 2,500–20,000 (soft target 3,500). H2 ≥ 6. FAQ 3–8.
9. Category in `VALID_WP_CATEGORY_IDS` (27, 28, 29, 30, 13, 14, 10).
10. ≥ 3 internal links biased toward audience-matching Tier-1.
11. ≥ 3 external dofollow links from `external_links.curated_for(category_id)`.
12. Three discovery provenance fields mandatory on every candidate: `discovery_source`, `discovery_id`, `discovery_evidence`.
13. Cannibalization gate: critical and high severity hard-block. Never propose them to Nikki.
14. Inventory snapshot ≤ 7 days old (`assert_fresh` raises otherwise).
15. Every WordPress call rejects any endpoint not on `firstmovers.ai`.

If `rubric.validate(draft)` raises a `ValueError`, the message names the exact rule violated. Fix the prose. Never silence the validation.

## MCP map

| MCP | Purpose | Critical tools |
|---|---|---|
| `mcp__first-movers-wordpress__*` | Inventory build + draft push | `wp_posts_search`, `wp_pages_search`, `wp_get_post`, `wp_get_page`, `wp_add_post`, `wp_users_search` |
| `mcp__ahrefs__*` | Inventory join + gap discovery + SERP intent | `site-explorer-organic-keywords`, `serp-overview`, `keywords-explorer-overview` |
| `mcp__gsc__*` | Striking-distance discovery | `get_search_analytics`, `get_search_by_page_query` |
| `mcp__claude_ai_searchable__*` | AEO discovery | `get_visibility_by_prompt`, `get_visibility_by_topic`, `get_visibility_summary` |
| `mcp__analytics-mcp__*` | GA4 high-traffic gap | `run_report`, `get_account_summaries` |
| `mcp__claude_ai_ClickUp__*` | Slate emit + approval read | `clickup_create_task`, `clickup_get_task`, `clickup_create_task_comment` |

## ClickUp identifiers (from `tools/identities.py`)

- Workspace: `9013404166`
- Content Projects list: `901326229295`
- Pipeline Status task: `86ah3ywyh`
- Nikki: `26221739`
- Josh: `120239313`

## When something breaks

| Symptom | Look here |
|---|---|
| Draft missing focus keyword in alt | `rubric._validate_image_with_focus_keyword_alt` — hero image alt is auto-generated, check that injection ran |
| WAF blocks WP push | Drafts queue to `data/runs/_pending-push/`. Run `gh workflow run wp-push-fallback.yml --ref main` to push from outside the WAF |
| Cannibalization gate refuses to run | Inventory is degraded (some post has `focus_keyword == None` or `organic_keywords == []`). Re-run `python -m tools.inventory_refresh` |
| Inventory > 7 days old | `assert_fresh` raises `StaleInventoryError`. Refresh before any draft |
| Title slate ends up with <12 proposals | Discovery sources didn't surface enough fresh candidates after cannibalization. Check that GSC + Ahrefs + Searchable + GA4 all returned data |

## What "Claude writes prose" means

When Phase 5 (`tools/draft.py`) needs to generate body text:

1. Load the rubric: invoke the `firstmovers-blog-rubric` skill via the `Skill` tool **before** writing.
2. Fetch SERP context: `mcp__ahrefs__serp-overview(keyword=focus_keyword)` to read the top-10 results.
3. Generate prose conforming to the rubric (≥2,500 words, ≥6 H2, focus keyword in lede + 1 H2 + 1 image alt, citation density, audience-routed CTA).
4. Run `rubric.validate(draft)`. On any `ValueError`, fix the named rule and re-validate. Don't push until the rubric passes clean.
