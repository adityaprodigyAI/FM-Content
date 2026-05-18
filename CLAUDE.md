# FM-Content — Operating Instructions

You are operating the **daily content automation pipeline for FirstMovers.ai**. It produces one high-quality WordPress blog draft per day for Nikki to review and publish. It runs unattended on an always-on VPS.

## The single most important rule

**Never propose a topic that overlaps a topic FirstMovers.ai has already published.** That was the v5 bug we rebuilt this pipeline to fix. The cannibalization gate (`tools/cannibalization.py`) is the structural defense — never weaken it, never bypass it, never run a draft on a stale or degraded inventory snapshot.

## The flow (always-on VPS cron — current production, 2026-05-17)

| When (Phoenix UTC-7) | Job | Runtime | What happens |
|---|---|---|---|
| Every day 07:00 | daily-idea | VPS cron → headless `claude -p` | All 4 discovery sources (Ahrefs + GSC + GA4 + Searchable) → cannibalization → 1 ClickUp task for Nikki |
| Continuous | (Nikki) | manual | Mark approved tasks "done" in ClickUp |
| Every 3 hours | polling-drafter | VPS cron → headless `claude -p` | Detect approvals → SERP + prose + rubric → push WP draft |
| Monday 05:00 | inventory-refresh | VPS cron → headless `claude -p` | Rebuild the published-content inventory snapshot |
| Every 12 hours | heartbeat | `/schedule` cloud | If no daily-idea task in last 36h, alert on `86ah3ywyh` |
| Continuous | (Nikki) | manual | Polish in WP, get Josh CTA approval, publish |

Phoenix is fixed offset UTC-7 year-round. No DST.

Runtime: the three jobs run as **system cron** on an always-on Hostinger VPS
(`187.77.146.79`, user `fmcontent`, Ubuntu 24.04, system timezone
America/Phoenix). Each cron tick runs headless Claude Code (`claude -p`) via
`~/fm-content/scripts/run-job.sh`, which reads the workflow file and executes
it. There is no `/loop`, no laptop session, and no re-registration — system
cron survives reboots. The `/schedule` cloud heartbeat is the independent canary
that alerts if the VPS itself goes down. Job logs are at
`~/fm-content/logs/*.log`. See `workflows/content-daily-idea-loop.md`,
`workflows/content-poll-and-draft-loop.md`,
`workflows/content-inventory-refresh.md`, `workflows/heartbeat-canary.md`, and
`docs/SYSTEM-HANDOVER.md`.

### Legacy weekly flow (deprecated 2026-05-12 — kept for reference only)

| Day (Phoenix UTC-7) | Job | What happens |
|---|---|---|
| ~~Sunday 07:00~~ | ~~`python -m tools.slate --week=NNNN-WNN --emit`~~ | superseded by daily-idea /loop |
| ~~Wednesday 09:00~~ | ~~`python -m tools.draft --week=NNNN-WNN --push`~~ | superseded by polling-drafter /loop |

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
16. **v1 ships text-only drafts.** No images in the body. To re-enable: see `tools/rubric.py::MIN_IMAGE_COUNT` (v1=0) and the rubric SKILL.md section 6.

If `rubric.validate(draft)` raises a `ValueError`, the message names the exact rule violated. Fix the prose. Never silence the validation.

## MCP map (as deployed on the VPS)

| Service | How it connects on the VPS | Critical tools |
|---|---|---|
| Ahrefs | claude.ai account connector | `site-explorer-organic-keywords`, `serp-overview`, `keywords-explorer-overview` |
| ClickUp | claude.ai account connector | `clickup_create_task`, `clickup_get_task`, `clickup_create_task_comment` |
| Searchable | claude.ai account connector | `get_visibility_by_prompt`, `get_visibility_by_topic`, `get_visibility_summary` |
| GSC | local `mcp-gsc` server (`~/mcp-gsc/`; OAuth token at `~/.config/mcp-gsc/token.json`) | `get_search_analytics`, `get_search_by_page_query` |
| WordPress | claude.ai FirstMoversWP connector for the draft push; `tools/push_wp.py` direct REST is the fallback if the connector is WAF-blocked | `wp_create_post`, `wp_update_post_meta` |
| GA4 | NOT an MCP — `tools/ga4.py` direct SDK with the service-account JSON at `GOOGLE_APPLICATION_CREDENTIALS` | `run_report` |
| ~~`mcp__analytics-mcp__*`~~ | hangs — DO NOT USE; use `tools/ga4.py` instead | — |

Tool-name note: the workflows were written with names like `mcp__ahrefs__*`; the
claude.ai connectors expose the same tools (sometimes under a `claude_ai_`
prefix). Use whichever tool name is actually available — the data is identical.

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
| Inventory > 7 days old | `assert_fresh` raises `StaleInventoryError`. The weekly inventory-refresh cron rebuilds it; to refresh now, run `python -m tools.inventory_refresh` on the VPS |
| daily-idea finds no clear candidate | Discovery sources came back thin after cannibalization. Check `~/fm-content/logs/daily-idea.log` and that GSC + Ahrefs + Searchable + GA4 all returned data |
| Jobs stopped firing entirely | Check the VPS: `crontab -l` lists the 3 jobs, `systemctl is-active cron`, and `claude -p "hi"` still works (subscription login can expire — re-run `claude` to re-login). The `/schedule` heartbeat will have alerted on `86ah3ywyh` |
| Need to see what a job did | VPS logs at `~/fm-content/logs/{daily-idea,polling-drafter,inventory-refresh}.log`; run-status comments on ClickUp task `86ah3ywyh` |

## What "Claude writes prose" means

When Phase 5 (`tools/draft.py`) needs to generate body text:

1. Load the rubric: invoke the `firstmovers-blog-rubric` skill via the `Skill` tool **before** writing.
2. Fetch SERP context: `mcp__ahrefs__serp-overview(keyword=focus_keyword)` to read the top-10 results.
3. Generate prose conforming to the rubric (≥2,500 words, ≥6 H2, focus keyword in lede + 1 H2, citation density, audience-routed CTA, **text-only — no images in the body**).
4. Run `rubric.validate(draft)`. On any `ValueError`, fix the named rule and re-validate. Don't push until the rubric passes clean.
