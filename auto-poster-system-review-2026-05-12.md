# FM-Content Auto-Poster — System Review

**Date:** 2026-05-12
**Status:** ✅ **Operational.** End-to-end MCP routing verified via manual test fire today at 07:49 UTC. Next natural cron fires: polling-drafter at 09:03 UTC (~60 min), daily-idea at 14:00 UTC (~6 hours).

---

## TL;DR — Is it working?

**Yes.** As of 07:49 UTC today, both required MCPs route correctly from the cloud routine, the routine starts, the discovery step calls Ahrefs successfully, the cannibalization/difficulty filter runs, and the routine reports back to ClickUp. The only reason today's run did not emit a topic is that today's competitor rotation (`bcg.com`) returned only high-difficulty (KD > 60) keywords — the routine correctly chose to skip rather than ship a low-quality post. **This is the system working, not failing.**

The natural 14:00 UTC fire today will repeat with the same result. The first "interesting" run is Wednesday 2026-05-13 14:00 UTC (`bain.com` rotation) — if any of its top-100 keywords clear the KD ceiling, you will see a real ClickUp task land in Nikki's queue.

---

## The two routines

| Routine | Cron (UTC) | Phoenix | Model | Last natural fire | Next natural fire |
|---|---|---|---|---|---|
| [`fm-content-daily-idea`](https://claude.ai/code/routines/trig_016QvCY5DUx7ZN4hPnN1aHZn) | `0 14 * * *` | 07:00 daily | `claude-sonnet-4-6` | never (registered 05-09, all prior fires failed at init) | 2026-05-12 14:00 UTC |
| [`fm-content-poll-and-draft`](https://claude.ai/code/routines/trig_01Cbbb7qwqadY3NudMkCWchV) | `0 */3 * * *` | every 3h | `claude-opus-4-7[1m]` | 2026-05-12 03:02 UTC (silent no-op) | 2026-05-12 09:03 UTC |

Both routines are **enabled** and have the corrected `mcp_connections` after today's fix.

---

## MCPs in use (the three connectors)

The `/schedule` cloud routine runs in a sandboxed environment that **blocks direct outbound HTTP** to non-allowlisted hosts (`api.ahrefs.com`, `api.clickup.com`, `firstmovers.ai/wp-json` are all blocked). The only way to reach those services from inside the routine is via the attached claude.ai MCP connectors. Their traffic routes through Anthropic's authenticated connector proxy, bypassing the sandbox restriction.

### 1. ClickUp MCP — `clickup_create_task`, `clickup_get_task`, `clickup_create_task_comment`

- **Connector uuid:** `37a27fca-ed4a-4ab5-af86-7448fc489f8d`
- **URL:** `https://mcp.clickup.com/mcp`
- **Used by:** both routines
- **Purpose:** emit the daily task for Nikki, poll for her approval, post status/canary/failure comments on the pipeline status task (`86ah3ywyh`)
- **Verified working:** today 07:49 UTC and 07:51 UTC — canary and final-status comments both posted successfully

### 2. Ahrefs MCP — `mcp__ahrefs__site-explorer-organic-keywords`, `mcp__ahrefs__serp-overview`

- **Connector uuid:** `09f92d25-0521-43d1-8b8e-d3124f9073e4`
- **URL:** `https://api.ahrefs.com/mcp/mcp`
- **Used by:** both routines
- **Purpose:**
  - daily-idea: pull a competitor's top-100 organic keywords for the day's competitor rotation (Mon mckinsey, Tue bcg, Wed bain, Thu hubspot, Fri accenture, Sat deloitte, Sun mckinsey)
  - polling-drafter: pull SERP overview for the focus keyword to inform prose generation
- **Verified working:** today 07:51 UTC — bcg.com keywords pulled, KD scores evaluated

### 3. FirstMoversWP MCP — `wp_create_post`, `wp_update_post_meta`

- **Connector uuid:** `d3546117-d69c-4fc4-9695-4948b0b9c9e9`
- **URL:** `https://firstmovers.ai/wp-json/royal-mcp/v1/mcp`
- **Used by:** polling-drafter only
- **Purpose:** create the WordPress draft post (`status=draft`, `post_author=3`/Josh McCoy) and set Rank Math meta (focus_keyword, seo_title, meta_description)
- **Verified working:** previously on 2026-05-08 (manual W20 backfill). Will be re-verified when the first end-to-end draft fires after this fix.

### MCPs intentionally NOT used in v1 (and why)

| MCP | Reason | When it returns |
|---|---|---|
| Google Search Console (`mcp__gsc__*`) | No claude.ai built-in connector for GSC. Either: build a `tools/gsc.py` SDK bypass (blocked by sandbox proxy in routine) OR set up a service-account auth flow through the connector layer (open work). | Phase 2, after the 2-routine system runs stable for a week. |
| Google Analytics 4 (`mcp__analytics-mcp__*`) | The MCP hangs (per CLAUDE.md rule). Direct SDK alternative `tools/ga4.py` is also blocked by the sandbox proxy. | Same as GSC — Phase 2. |
| Searchable AEO (`mcp__claude_ai_searchable__*`) | Available in your authorized connectors but not wired into the v1 routines yet (Ahrefs gap alone produces enough signal for testing). | Could be added as a second discovery leg in a follow-up. |
| Fathom (sales objections) | MCP available, not needed for v1 discovery. | Plan v2 (HTML spec) had this as a fourth discovery leg. |

---

## How content is generated

### Daily idea (every day 07:00 Phoenix = 14:00 UTC)

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. CANARY                                                            │
│    clickup_create_task_comment on 86ah3ywyh                          │
│    proves: ClickUp MCP healthy this run                              │
├──────────────────────────────────────────────────────────────────────┤
│ 2. IDEMPOTENCY                                                       │
│    if data/runs/_daily/<TODAY>.json exists: skip + exit 0            │
├──────────────────────────────────────────────────────────────────────┤
│ 3. INVENTORY FRESHNESS                                               │
│    python -m tools.inventory_refresh --check                         │
│    fails closed if snapshot >7 days old                              │
├──────────────────────────────────────────────────────────────────────┤
│ 4. DISCOVERY (rotated competitor)                                    │
│    mcp__ahrefs__site-explorer-organic-keywords(                      │
│      target=<today's competitor>, mode=subdomains,                   │
│      limit=100, order_by=sum_traffic:desc)                           │
│    -> top-100 keywords by traffic                                    │
├──────────────────────────────────────────────────────────────────────┤
│ 5. FILTER                                                            │
│    tools.discover.ahrefs_gap.discover() converts keywords            │
│      to Candidate objects with categorization + audience routing     │
│    tools.cannibalization.evaluate() drops any candidate that         │
│      overlaps existing inventory (slug, focus_keyword,               │
│      title >70% similarity, canonical conflict)                      │
│    KD ceiling: keywords with difficulty > 60 are skipped             │
├──────────────────────────────────────────────────────────────────────┤
│ 6. PICK TOP-1                                                        │
│    tools.daily.pick_top_candidate(clear) - source-weighted score     │
│    if None survives -> comment "no candidates" + exit                │
├──────────────────────────────────────────────────────────────────────┤
│ 7. GENERATE TITLE + ANGLE + OUTLINE                                  │
│    Sonnet writes ≤120 char title, 1-line angle, 3 H2 bullets         │
│    enforces: no em dashes, no trailing period, no "free audit"       │
├──────────────────────────────────────────────────────────────────────┤
│ 8. PERSIST STATE                                                     │
│    DailyState(date, proposal) -> data/runs/_daily/<TODAY>.json       │
├──────────────────────────────────────────────────────────────────────┤
│ 9. EMIT CLICKUP TASK                                                 │
│    clickup_create_task(list_id=901326229295,                         │
│      name=f"[{TODAY}] {working_title}",                              │
│      assignees=[26221739 = Nikki],                                   │
│      tags=["fm-content-daily"])                                      │
│    state.clickup_task_id = resp.id                                   │
├──────────────────────────────────────────────────────────────────────┤
│ 10. STATUS COMMENT + GIT PUSH                                        │
│    final comment on 86ah3ywyh with link to the new task              │
│    git commit data/runs/_daily/ and push to main                     │
└──────────────────────────────────────────────────────────────────────┘
```

**No prose is generated at this stage** — only the title, angle, and outline. Nikki sees these in ClickUp and decides whether to approve the topic.

### Polling drafter (every 3 hours)

Triggered by the cron schedule independently of the daily idea routine.

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. LIST PENDING WORK                                                 │
│    pending_approvals() - states emitted but not yet approved         │
│    pending_drafts() - states approved but not yet drafted            │
│    if both empty: exit 0 silently (no canary, no log)                │
├──────────────────────────────────────────────────────────────────────┤
│ 2. CHECK CLICKUP FOR APPROVALS                                       │
│    for each pending approval:                                        │
│      resp = clickup_get_task(state.clickup_task_id)                  │
│      if status.type ∈ {"done","closed"} or status.name ∈            │
│        {"published","complete","closed","done","ready"}:             │
│          mark_approved(state)                                        │
├──────────────────────────────────────────────────────────────────────┤
│ 3. DRAFT THE APPROVED TOPICS                                         │
│    for each pending draft:                                           │
│      prepare_brief(prop, inv) [cannibalization re-check]             │
│      mcp__ahrefs__serp-overview(focus_keyword) - top 10 SERP         │
│      Skill(skill='firstmovers-blog-rubric') [loads brand voice]      │
│      Claude Opus 4.7 writes 2500-3500 word body_html + 3-7 FAQ +     │
│        seo_title (≤60 chars) + meta_description (≤155 chars)         │
│      assemble(brief, body_html, faq_items, seo_title, meta_desc)     │
│        -> validates 19 rubric rules                                  │
│        -> raises RubricViolation on any failure                      │
│        -> agent retries up to 2x with feedback                       │
├──────────────────────────────────────────────────────────────────────┤
│ 4. PUSH TO WORDPRESS                                                 │
│    wp_create_post(status='draft', post_author=3 /Josh/)              │
│    wp_update_post_meta(rank_math_focus_keyword,                      │
│                         rank_math_title,                             │
│                         rank_math_description)                       │
├──────────────────────────────────────────────────────────────────────┤
│ 5. NOTIFY NIKKI                                                      │
│    clickup_create_task_comment on her daily task:                    │
│      edit_url, preview_url, word count, "review + publish" prompt    │
├──────────────────────────────────────────────────────────────────────┤
│ 6. STATUS + GIT PUSH                                                 │
│    summary on 86ah3ywyh + commit data/runs/_daily/                   │
└──────────────────────────────────────────────────────────────────────┘
```

**Prose generation happens here** — Claude Opus 4.7 (1M context) generates the actual blog body, FAQ items, SEO title, and meta description, validated against 19 rubric rules in `tools/rubric.py`.

---

## How the autonomous loop actually flows

```
Day N        07:00 Phoenix    daily-idea fires
                              ↓
                              picks a topic from competitor-N's keywords
                              emits ClickUp task [N] in Nikki's queue
                              (state: emitted)

Day N-N+2    any time         Nikki sees the task in ClickUp
                              changes status to "published" / "done" / "complete"
                              (this is THE ONLY MANUAL TOUCH in the loop)

Day N        next /3h         polling-drafter fires
                              sees state=emitted, polls ClickUp -> done
                              advances state: emitted -> approved
                              (state: approved)

                              same run: sees state=approved, generates prose
                              validates rubric, pushes to WP as draft
                              comments back with edit URL
                              (state: drafted)

Day N+2..    Nikki polishes   adds featured image, gets Josh CTA approval,
             draft in WP      publishes to firstmovers.ai
```

**One manual touch per topic: Nikki's ClickUp status change.** Everything else is autonomous.

---

## Today's verification evidence

| When (UTC) | What | Result |
|---|---|---|
| 07:44 | I attached connectors + reverted prompts to MCP via `RemoteTrigger.update` | ✅ HTTP 200 |
| 07:46 | I pushed corrected workflow files to main (commit `f17915e`) | ✅ pushed |
| 07:48 | I triggered manual fire via `RemoteTrigger.run` on daily-idea | ✅ HTTP 200 |
| 07:49 | Canary comment posted on `86ah3ywyh` | ✅ **ClickUp MCP works** |
| 07:51 | Status comment: "no clear candidates from bcg.com" | ✅ **Ahrefs MCP works + filter logic ran** |

**What this evidence does NOT prove yet:** The end-to-end emit + draft path, because today's bcg.com rotation produced no viable candidate. That portion gets exercised the first day a competitor's keyword list yields at least one candidate with KD ≤ 60 — most likely tomorrow's bain.com rotation, or hubspot.com on Thursday.

---

## Pipeline status task to watch

**ClickUp task `86ah3ywyh`** ("📊 Content Pipeline Status (automation board)") is the **monitoring surface**. Every routine fire posts a comment there:

- ✅ "Routine fm-content-daily-idea started at..." → canary, proves the run kicked off
- ✅ "Daily idea YYYY-MM-DD emitted: '<title>' (focus_kw: ..., score: ..., ClickUp: ...)" → success
- 🟡 "Daily idea YYYY-MM-DD: no clear candidates from <competitor>..." → graceful skip (today's case)
- ❌ "Daily idea YYYY-MM-DD FAILED: ..." → fix needed; the comment describes what broke
- 🟢 "Polling drafter run: N newly approved, M drafted, K still awaiting" → polling-drafter cycle complete

**If a routine fires and you see NO comment within 5 minutes**, that means the routine couldn't even reach step 0 — most likely a connector binding issue.

---

## Pipeline configuration snapshot

```yaml
inventory_snapshot:
  path: data/inventory/firstmovers-ai.json
  generated_at: 2026-05-08T08:58:47 UTC   # 4 days old, fresh (≤7d)
  posts: 157
  pages: 0

clickup_pipeline_status_task: 86ah3ywyh    # all routine logs go here
clickup_content_projects_list: 901326229295  # where daily tasks land for Nikki

assignees:
  nikki: 26221739    # only person who marks approval
  josh:  120239313

wordpress:
  author: 3 (Josh McCoy)
  status_on_create: draft (never publish from the routine)
  categories_in_use: [27, 28, 29, 30, 13, 14, 10]

competitor_rotation:
  Monday:    mckinsey.com
  Tuesday:   bcg.com         # today's run
  Wednesday: bain.com
  Thursday:  hubspot.com
  Friday:    accenture.com
  Saturday:  deloitte.com
  Sunday:    mckinsey.com

cannibalization_thresholds:
  slug_exact_match:    drop
  focus_kw_exact:      drop
  title_similarity:    drop ≥ 70%
  canonical_conflict:  drop
  keyword_difficulty:  drop > 60

rubric_checks: 19   # tools/rubric.py — assemble() enforces all
```

---

## Known limitations / what's NOT bulletproof yet

| # | Limitation | Severity | Mitigation |
|---|---|---|---|
| L1 | Today's bcg.com rotation yielded no candidates. Each Tuesday may keep being a no-op. | Low — graceful skip, no bad content. | Watch for a week. If 2+ days/week skip, lower KD ceiling or replace bcg.com in rotation. |
| L2 | A natural fire after a manual fire on the same day will re-run the same competitor and post a duplicate "no candidates" comment (because no state file exists when no emit happened). | Cosmetic — duplicate noise on `86ah3ywyh`. | v1.1 patch: write a `no_emit` state file on graceful skip to short-circuit re-runs. |
| L3 | GSC, GA4, Searchable, Fathom not wired into discovery. Single signal (Ahrefs competitor gap) is thin. | Medium — quality of candidate pool. | Phase 2: add Searchable AEO as second leg (the connector is already authorized). GSC needs a separate plan (no claude.ai connector exists yet). |
| L4 | If the Ahrefs MCP connector uuid `09f92d25` is ever rotated, the routine breaks silently. | Medium. | The canary failure pattern makes this detectable within minutes via `86ah3ywyh`. |
| L5 | Rubric validation may reject a draft 2x in a row; on third failure the topic is parked. Nikki has to manually escalate. | Low — quality gate doing its job. | Acceptable for v1. Could expose a "rubric_failed" tag on the ClickUp task for visibility. |
| L6 | The cloud routine sandbox has no self-serve allowlist. If a new MCP becomes necessary, only Anthropic-managed connectors will work; new direct-REST integrations need a different runtime (e.g., GitHub Actions). | Architectural. | Plan v2 (HTML spec) proposed GitHub Actions as the primary runtime for exactly this reason. Defer unless we hit a hard blocker. |

---

## Verification plan from here

You asked to confirm autonomy with a **scheduled** (not manual) run. Two natural fires happen today:

| When (UTC) | Routine | Expected outcome |
|---|---|---|
| **2026-05-12 09:03 UTC** (~60 min from now) | `fm-content-poll-and-draft` | Silent no-op. No pending state exists today. The cron `last_fired_at` field will advance from `03:02 UTC` to `09:03 UTC`, confirming the natural fire is healthy. No ClickUp comments expected (per prompt's "exit silently if no work"). |
| **2026-05-12 14:00 UTC** (~6 hours from now) | `fm-content-daily-idea` | Will repeat today's bcg.com run. Same "no clear candidates" comment expected. `last_fired_at` will advance from `None` to `14:00 UTC`, **confirming the natural cron fires the corrected routine end-to-end**. |

**Recommendation:** read this doc, sign off if it matches your understanding, then we wait for the 14:00 UTC fire. I'll come back and verify a fresh comment appears on `86ah3ywyh` from that scheduled run, proving the autonomous loop is healthy without any manual intervention.

If you want to test the EMIT path before bain.com on Wednesday, two options:
- **(a)** Temporarily raise the KD ceiling to 80 in `tools/discover/ahrefs_gap.py` for one day, then revert — would force a topic from today's bcg.com keyword pool.
- **(b)** Manually inject a known-good `data/runs/_daily/2026-05-12.json` with a hand-picked candidate, then trigger the polling-drafter to verify prose generation + WP draft creation in isolation.

Otherwise just wait until **Wednesday 14:00 UTC** for the bain.com rotation — that's the first natural opportunity for an end-to-end emit.

---

## Sign-off questions for you

Before we declare this done, confirm:

1. The three MCPs (FirstMoversWP, ClickUp, Ahrefs) match what you expected.
2. The single manual touch in the loop (Nikki's ClickUp status change) is acceptable as v1.
3. You're comfortable with the bcg.com Tuesday being a frequent no-emit day until we widen the signal.
4. The competitor rotation looks right (or you want to swap any of them).
5. You want to wait for the natural 14:00 UTC fire today as the autonomous-run proof, OR pre-test the emit path via option (a) or (b) above.

When you've reviewed, paste "looks good" and I'll set up a wakeup to verify the 14:00 UTC natural fire and report back.
