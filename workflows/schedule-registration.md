# `/schedule` registration — daily-idea + polling-drafter cron

> **DEPRECATED for production (2026-05-12).** The two routines documented below are kept for reference only. Production flow has migrated to `/loop` running in the operator's local Claude Code session, with all 4 discovery sources (Ahrefs + GSC + GA4 + Searchable) instead of Ahrefs-only:
>
> - `workflows/content-daily-idea-loop.md` — `/loop` daily-idea
> - `workflows/content-poll-and-draft-loop.md` — `/loop` polling-drafter
> - `workflows/heartbeat-canary.md` — the one `/schedule` routine still in use (safety-net heartbeat)
>
> The two `/schedule` routines below remain registered during the 7-day cutover window (2026-05-13 through 2026-05-19) for safety. After successful cutover, run `/schedule update fm-content-daily-idea enabled=false` and `/schedule update fm-content-poll-and-draft enabled=false`. Dual-mode safety relies on `tools.daily.should_skip_for_clickup_dup` to prevent double-emission while both are active.
>
> Future VM migration may revisit /loop vs cron+claude -p as the runtime mechanism.

> Copy-paste invocations to register the two FM-Content cron routines via Claude Code's `/schedule` skill. Each routine is a remote Claude agent that runs on cron in claude.ai's cloud sandbox.

## Critical constraint — routine sandbox proxy

The `/schedule` cloud routine runs in a sandboxed environment that **blocks outbound HTTP to non-allowlisted domains**. Direct HTTP to `api.ahrefs.com`, `api.clickup.com`, or `firstmovers.ai/wp-json` returns `HTTP 403 "Host not in allowlist"` from the sandbox proxy. The only way to reach those services from inside the routine is via the **attached claude.ai MCP connectors** — the connector traffic is routed through claude.ai's authenticated proxy infrastructure, which bypasses the sandbox network restriction.

There is no self-serve allowlist for routine network access as of 2026-05-12 (filed as a closed-duplicate feature request on github.com/anthropics/claude-code).

**Implication:** All external calls in the routine prompts MUST use the bare MCP tool names (`clickup_create_task`, `mcp__ahrefs__site-explorer-organic-keywords`, `wp_create_post`, etc.) — NOT the direct-REST wrappers in `tools/clickup.py` or `tools/ahrefs.py` (those are for local development only).

## TL;DR

| Routine name | Cron (UTC) | Phoenix time | Purpose |
|---|---|---|---|
| `fm-content-daily-idea` | `0 14 * * *` | 07:00 daily | Pick one new topic, emit ClickUp task for Nikki |
| `fm-content-poll-and-draft` | `0 */3 * * *` | every 3h | Detect approvals, generate prose, push WP drafts |

After Nikki marks any daily task with a "done"-type status name in ClickUp, the polling drafter picks it up within 3 hours and produces a fully validated WordPress draft.

## MCP connections to attach (required)

| Connector | UUID | URL | Used by |
|---|---|---|---|
| FirstMoversWP | `d3546117-d69c-4fc4-9695-4948b0b9c9e9` | `https://firstmovers.ai/wp-json/royal-mcp/v1/mcp` | polling-drafter only (`wp_create_post`, `wp_update_post_meta`) |
| ClickUp | `37a27fca-ed4a-4ab5-af86-7448fc489f8d` | `https://mcp.clickup.com/mcp` | both (`clickup_create_task`, `clickup_get_task`, `clickup_create_task_comment`) |
| Ahrefs | `09f92d25-0521-43d1-8b8e-d3124f9073e4` | `https://api.ahrefs.com/mcp/mcp` | both (`mcp__ahrefs__site-explorer-organic-keywords`, `mcp__ahrefs__serp-overview`) |

If any of these uuids no longer resolve (e.g., the user revoked + re-added the connector and got a fresh uuid), check current connector state via `/schedule list` and look at the `mcp_connections` of the working routines, or re-attach via the claude.ai connectors page.

## Env vars at registration

None required for the cloud routines — all external calls go through MCP connectors. Local development can still use `AHREFS_API_TOKEN` and `CLICKUP_API_TOKEN` env vars for the direct-REST wrappers in `tools/ahrefs.py` and `tools/clickup.py`.

---

## Routine 1 — `fm-content-daily-idea`

**Cron:** `0 14 * * *` UTC (07:00 America/Phoenix, fixed offset UTC-7 year-round)

**Model:** `claude-sonnet-4-6` (sufficient for topic picking; opus is overkill here)

**Prompt** (paste verbatim):

```text
FM-Content daily-idea routine. Full SOP: workflows/content-daily-idea.md (READ THIS FIRST and follow it exactly).

Setup:
  pip install -e .

Note: This routine uses the attached MCP connectors (ClickUp, Ahrefs) for all external calls. Direct HTTP to api.ahrefs.com or api.clickup.com is BLOCKED by the routine sandbox proxy ('Host not in allowlist'). The MCP route via the attached connectors bypasses this restriction.

Compute today (Phoenix, fixed UTC-7 year-round):
  TODAY=$(python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Phoenix')).strftime('%Y-%m-%d'))")
  DOW=$(python -c "from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo('America/Phoenix')).strftime('%A'))")

WORKFLOW:

0. Canary comment via MCP: clickup_create_task_comment(task_id='86ah3ywyh', comment_text=f'Routine fm-content-daily-idea started at {TODAY} (UTC: <iso-now>)').

1. Idempotency check: if data/runs/_daily/${TODAY}.json exists, comment 'Daily idea ${TODAY}: already emitted, skipping.' and exit 0.

2. Inventory freshness: python -m tools.inventory_refresh --check. If non-zero, comment failure to 86ah3ywyh and exit non-zero.

3. Discovery via Ahrefs MCP. Rotate competitor by $DOW:
     Mon -> mckinsey.com, Tue -> bcg.com, Wed -> bain.com, Thu -> hubspot.com,
     Fri -> accenture.com, Sat -> deloitte.com, Sun -> mckinsey.com
   Call: mcp__ahrefs__site-explorer-organic-keywords(target=<competitor>, mode='subdomains', date=$TODAY, limit=100, order_by='sum_traffic:desc', select='keyword,best_position,best_position_url,sum_traffic,volume,keyword_difficulty')

4. Parse + filter + pick top-1 (Python):
     from tools.discover.ahrefs_gap import discover as ahrefs_discover
     from tools.daily import pick_top_candidate, candidate_to_proposal_dict, DailyState, save_state, mark_emitted
     from tools.cannibalization import ProposedTopic, evaluate
     from tools.inventory import load
     inv = load(); inv.assert_fresh(); inv.assert_complete()
     translated = [{...standard shape...} for kw in <ahrefs>["keywords"]]
     candidates = ahrefs_discover(<competitor>, {"keywords": translated}, inv)
     clear = [c for c in candidates if evaluate(ProposedTopic(...), inv).severity not in ('critical','high')]
     top = pick_top_candidate(clear)
     if top is None: comment 'no clear candidates' and exit 0.

5. Generate working_title (<=120 chars, no trailing period, no em dashes, no 'free audit'), one-line angle, three H2-starter outline bullets.

6. Save daily state:
     proposal = candidate_to_proposal_dict(top, title=<title>, angle=<angle>, outline=<outline>, target_date=TODAY)
     state = DailyState(date=TODAY, proposal=proposal); save_state(state)

7. Emit ONE ClickUp task via MCP:
     resp = clickup_create_task(list_id='901326229295', name=f'[{TODAY}] {proposal["working_title"]}',
                                 markdown_description=<rich block>, assignees=[26221739],
                                 due_date=TODAY, tags=['fm-content-daily'])
     state = mark_emitted(state, task_id=resp.get('task_id') or resp.get('id')); save_state(state)

8. Status comment on 86ah3ywyh via clickup_create_task_comment.

9. git add data/runs/_daily/ && git commit && git push (best effort).

HARD RULES: status=draft only, no 'free audit', no em dashes, no trailing period in titles, audience routing DFY->/consulting/ DIY->/labs/.

DO NOT call api.clickup.com or api.ahrefs.com directly — use the attached MCP tools.
ON FAILURE: comment to 86ah3ywyh and exit non-zero.
```

---

## Routine 2 — `fm-content-poll-and-draft`

**Cron:** `0 */3 * * *` UTC (every 3 hours)

**Model:** `claude-opus-4-7[1m]` (1M context for long prose generation + rubric checks)

**Prompt** (paste verbatim):

```text
FM-Content polling-drafter routine. Full SOP: workflows/content-poll-and-draft.md (READ THIS FIRST and follow it exactly).

Setup:
  pip install -e .

Note: Uses attached MCP connectors (ClickUp, Ahrefs, FirstMoversWP) for all external calls. Direct HTTP to api.ahrefs.com, api.clickup.com, firstmovers.ai/wp-json is BLOCKED by routine sandbox proxy ('Host not in allowlist').

WORKFLOW:

0. List pending work:
     python -m tools.daily pending-approvals
     python -m tools.daily pending-drafts
   If both empty, exit 0 silently.

1. Canary (only if pending work): clickup_create_task_comment(task_id='86ah3ywyh', comment_text='Routine fm-content-poll-and-draft started at <iso-now>')

2. For each pending approval (state.is_emitted and not state.is_approved):
     resp = clickup_get_task(task_id=state.clickup_task_id, detail_level='summary')
     from tools.daily import is_task_approved, mark_approved, save_state
     approved, status_name = is_task_approved(resp)
     if approved: mark_approved(state, status_name=status_name); save_state(state)

3. For each pending draft (state.is_approved and not state.is_drafted):
     from tools.slate import SlateProposal
     from tools.draft import prepare_brief, assemble
     from tools.inventory import load
     from tools.rubric import FaqItem, RubricViolation
     from tools.push_wp import build_create_payload
     from tools.rank_math import build_meta
     from tools.daily import mark_drafted

     inv = load(); inv.assert_fresh(); inv.assert_complete()
     prop = SlateProposal(**state.proposal)
     brief = prepare_brief(prop, inv)   # cannibalization re-check

     serp = mcp__ahrefs__serp-overview(keyword=prop.focus_keyword, country='us', top_positions=10,
                                        select='title,url,position,domain_rating,backlinks,traffic,top_keyword')

     # Load rubric: Skill(skill='firstmovers-blog-rubric')
     # Generate body_html (2500-3500 words, >=6 H2, focus_kw in lede + >=1 H2, >=3 dofollow citations, no em dashes, no 'free audit'), faq_items, seo_title, meta_description.

     try:
       assembled = assemble(brief, body_html=<body>, faq_items=<faqs>, seo_title=<seo>, meta_description=<meta>)
     except RubricViolation as e: ... retry up to 2x ...

     wp = wp_create_post(title=assembled.title, content=assembled.body_html, excerpt=assembled.excerpt,
                         status='draft', categories=[assembled.category_id], post_author=3)
     post_id = int(wp['id'])
     edit_url = f'https://firstmovers.ai/wp-admin/post.php?post={post_id}&action=edit'

     rm = build_meta(focus_keyword=assembled.focus_keyword, seo_title=assembled.seo_title,
                     meta_description=assembled.meta_description, slug=assembled.slug)
     for k, v in [('rank_math_focus_keyword', rm.focus_keyword),
                  ('rank_math_title', rm.seo_title),
                  ('rank_math_description', rm.meta_description)]:
       wp_update_post_meta(post_id=post_id, key=k, value=v)

     mark_drafted(state, post_id=post_id, edit_url=edit_url); save_state(state)

     clickup_create_task_comment(task_id=state.clickup_task_id,
       comment_text=f"Drafted to WordPress.\n\n- Edit: {edit_url}\n- Preview: https://firstmovers.ai/?p={post_id}&preview=true\n- Word count: {wc:,}\n- Author: Josh McCoy (post_author=3)\n\nNikki: review, set slug to '{assembled.slug}' if needed, add featured image, get Josh CTA approval, publish, NitroPack purge.")

4. Status comment on 86ah3ywyh (only if any state advanced):
     clickup_create_task_comment(task_id='86ah3ywyh', comment_text=f'Polling drafter run: <N> newly approved, <M> drafted, <K> still awaiting.')

5. git add data/runs/_daily/ && git commit && git push (best effort).

HARD RULES: status=draft only, post_author=3 (Josh McCoy), no 'free audit', no em dashes, no trailing period in titles, audience CTAs DFY->/consulting/ DIY->/labs/, 19 rubric checks all pass, cannibalization critical/high = hard block.

FAILURE HANDLING:
- CannibalizationError on prepare_brief: comment on the ClickUp task, skip the draft.
- RubricViolation on assemble: regenerate up to 2x; on third failure, note and skip.
- WAF block on wp_create_post: queue to data/runs/_pending-push/ via tools.push_wp.queue_for_path_b, trigger wp-push-fallback.yml via gh CLI. Leave state at 'approved'.

IDEMPOTENCY:
- State already DRAFTED (wp_post_id set) -> skip silently.
- State PENDING (no clickup_task_id) -> skip (daily-idea handles it).

DO NOT call api.clickup.com, api.ahrefs.com, or firstmovers.ai/wp-json directly — use the attached MCP tools.
```

---

## After registration

Verify both routines are registered (via `/schedule` skill):

```
fm-content-daily-idea       0 14 * * *      next: <upcoming 14:00 UTC>     mcp: FirstMoversWP, ClickUp, Ahrefs
fm-content-poll-and-draft   0 */3 * * *     next: <upcoming :00 UTC>       mcp: FirstMoversWP, ClickUp, Ahrefs
```

The daily-idea routine fires once tomorrow morning Phoenix time. The polling drafter fires every 3 hours and is a no-op until the daily routine emits the first task and Nikki approves it.

## Local development vs cloud routine

| Surface | ClickUp | Ahrefs | WordPress |
|---|---|---|---|
| **Cloud routine** (`/schedule`) | `clickup_*` MCP tools (ClickUp connector) | `mcp__ahrefs__*` MCP tools (Ahrefs connector) | `wp_*` MCP tools (FirstMoversWP connector) |
| **Local dev** (Claude Code session, pytest, ad-hoc scripts) | `tools.clickup.create_task` etc. (direct REST with `CLICKUP_API_TOKEN` env) | `tools.ahrefs.fetch_organic_keywords` etc. (direct REST with `AHREFS_API_TOKEN` env) | `tools.push_wp` (REST API or MCP, either works) |

The direct-REST wrappers in `tools/clickup.py` and `tools/ahrefs.py` are for local-only use. Calling them from the cloud routine prompt will fail with `403 Host not in allowlist` because the routine sandbox proxy blocks the outbound HTTP.

## Switching back to weekly mode later

When you're ready to leave testing and go to the production weekly cycle:

```
/schedule update fm-content-daily-idea     enabled=false
/schedule update fm-content-poll-and-draft enabled=false
/schedule create  ...   # use workflows/content-sunday-slate.md      (cron 0 14 * * 0)
/schedule create  ...   # use workflows/content-wednesday-draft.md   (cron 0 16 * * 3)
```

The daily mode does not interfere with the weekly mode — they share state files in `data/runs/_daily/` and `data/runs/_title-slates/` respectively. Switching is just a matter of which routines are enabled.

## Diagnostic playbook

If a routine appears to never fire (no comments on `86ah3ywyh`, no `data/runs/_daily/<date>.json` files):

1. Check registration: `/schedule list` should show the routine with `enabled: true`.
2. Check `last_fired_at` — non-null means the cron schedule is firing.
3. Check `mcp_connections` includes the required connectors (FirstMoversWP, ClickUp, Ahrefs).
4. Check ClickUp pipeline status task `86ah3ywyh` for failure comments — the agent posts them on most failure modes.
5. If `last_fired_at` is set but no comments: the canary step failed. Likely a missing or misconfigured MCP connector (the connector_uuid may have become invalid).
6. If failure comments mention `403 "Host not in allowlist"`: the prompt or workflow is trying direct HTTP to a non-allowlisted host. Switch that call to the MCP equivalent.
