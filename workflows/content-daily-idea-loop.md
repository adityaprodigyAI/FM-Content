# Daily idea — /loop variant (runs in operator's local Claude Code, all 4 discovery sources)

> **Goal.** Once per day (target: 07:00 in the client's content timezone), post ONE blog topic to ClickUp for the approver to review. Uses all 4 discovery sources (Ahrefs gap + GSC striking-distance + GA4 decay + Searchable AEO).
>
> All client-specific values (content timezone, approver, ClickUp ids, GSC/GA4/Searchable targets, competitor rotation) come from `client_config.toml`. This workflow hardcodes none of them.

> **Runtime.** Register with `/loop` inside the operator's local Claude Code session, using the cron in `client_config.toml` → `schedule.daily_idea_local_cron` (already converted to the operator's local timezone — see `schedule.operator_timezone`). The state-file idempotency guarantees only one emit per content-timezone day even if firing drifts by a few hours.

> **Why /loop not /schedule.** Three of the four discovery sources (GSC, GA4, Searchable) are not reachable from the /schedule sandbox proxy. The /loop runs in the operator's local Claude Code session where all local MCPs work. VM hosting is a future plan; for now the /loop fires only when Claude Code is open.

---

## Inputs

- Today's date in the client's content timezone (state file is keyed by it)
- Inventory snapshot at `data/inventory/<site-host>.json` (e.g. `firstmovers-ai.json`) — must be fresh (≤7 days old)

If inventory is stale, refresh first per `workflows/content-inventory-refresh.md`.

---

## Step-by-step

### 1. Idempotency check + canary

```python
import sys; sys.path.insert(0, ".")
from tools.daily import DAILY_DIR
# Every client-specific id/url/timezone comes from client_config.toml via
# tools.identities. Never hardcode a client value in this workflow.
from tools.identities import (
    APPROVER_CLICKUP_USER_ID,
    CONTENT_PIPELINE_STATUS_TASK_ID,
    CONTENT_PROJECTS_LIST_ID,
    CONTENT_TIMEZONE,
    GSC_SITE_URL,
    SEARCHABLE_PROJECT_ID,
    competitor_for_weekday,
)
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.now(ZoneInfo(CONTENT_TIMEZONE)).strftime("%Y-%m-%d")
state_path = DAILY_DIR / f"{today}.json"
if state_path.exists():
    # idempotent skip
    Skill(skill="fm-clickup-ops")
    clickup_create_task_comment(
        task_id=CONTENT_PIPELINE_STATUS_TASK_ID,
        comment_text=f"Daily idea {today}: already emitted, skipping.",
    )
    sys.exit(0)
```

### 1a. Dual-mode cutover safety — check ClickUp for cloud-emitted dup

> **Remove this block after the 7-day cutover window closes and the old /schedule routines are disabled.**

```python
from tools.daily import should_skip_for_clickup_dup, DailyState, mark_emitted, save_state

skip, existing_task_id = should_skip_for_clickup_dup(
    today=today, clickup_search_fn=clickup_search,
)
if skip:
    # cloud routine already emitted; mirror into local state so polling-drafter
    # picks it up via the local pending_approvals() iterator
    Skill(skill="fm-clickup-ops")
    resp = clickup_get_task(task_id=existing_task_id, detail_level="summary")
    # minimal proposal reconstruction from the task description; the polling
    # drafter only needs `working_title`, `focus_keyword`, `audience`, etc.
    proposal = parse_proposal_from_task(resp)  # implement inline or skip if rich
    state = DailyState(date=today, proposal=proposal)
    state = mark_emitted(state, task_id=existing_task_id)
    save_state(state)
    clickup_create_task_comment(
        task_id=CONTENT_PIPELINE_STATUS_TASK_ID,
        comment_text=f"Daily idea {today}: cloud routine already emitted task {existing_task_id}; mirrored to local state.",
    )
    sys.exit(0)
```

### 2. Verify inventory freshness

```python
from tools.inventory_refresh import freshness_check
assert freshness_check() == 0, "inventory stale — refresh first"
```

### 3. Load discovery skills

```
Skill(skill="fm-ahrefs")
Skill(skill="fm-gsc")
Skill(skill="fm-ga4")
Skill(skill="fm-searchable")
Skill(skill="fm-cannibalization")
```

### 4. Pull all 4 discovery signals

```python
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

today_dt = datetime.now(ZoneInfo(CONTENT_TIMEZONE))
today = today_dt.strftime("%Y-%m-%d")
twenty_eight_ago = (today_dt - timedelta(days=28)).strftime("%Y-%m-%d")

# Competitor rotation comes from client_config.toml [discovery] — Mon=0..Sun=6.
competitor = competitor_for_weekday(today_dt.weekday())

# Ahrefs gap (competitor rotation)
ahrefs_resp = mcp__ahrefs__site-explorer-organic-keywords(
    target=competitor, mode="subdomains", date=today,
    limit=100, order_by="sum_traffic:desc",
    select="keyword,best_position,best_position_url,sum_traffic,volume,keyword_difficulty",
)

# GSC striking distance
gsc_resp = mcp__gsc__get_search_analytics(
    site_url=GSC_SITE_URL,
    start_date=twenty_eight_ago,
    end_date=today,
    dimensions=["query", "page"],
    row_limit=500,
    data_state="final",
)

# GA4 decay (direct SDK — mcp__analytics-mcp hangs, do not use)
# Note: real signature uses `days=N` not date_ranges; the default property_id
# inside tools/ga4.py is sourced from client_config.toml [ga4].property_id.
# Wrap in try/except since GA4 auth (service-account / gcloud ADC) may be
# expired — degrade gracefully if so.
ga4_rows = None
try:
    from tools.ga4 import run_report
    ga4_rows = run_report(
        dimensions=["pagePath"],
        metrics=["sessions", "engagedSessions"],
        days=28,
        limit=500,
    )
except Exception as e:
    # log + continue with remaining 3 discovery sources
    print(f"GA4 unavailable, skipping decay discovery: {type(e).__name__}: {e}")

# Searchable AEO
searchable_resp = mcp__claude_ai_searchable__get_visibility_by_topic(
    project_id=SEARCHABLE_PROJECT_ID,
)
```

### 5. Merge candidates + run cannibalization gate

```python
from tools.discover.ahrefs_gap import discover as ahrefs_discover
from tools.discover.gsc import discover as gsc_discover
from tools.discover.ga4_gap import discover as ga4_discover
from tools.discover.searchable_aeo import discover as searchable_discover
from tools.cannibalization import ProposedTopic, evaluate
from tools.inventory import load
from tools.daily import pick_top_candidate, candidate_to_proposal_dict

inv = load()
inv.assert_fresh()
inv.assert_complete()

translated = [
    {"keyword": kw["keyword"], "position": kw.get("best_position"),
     "traffic": kw.get("sum_traffic", 0), "volume": kw.get("volume", 0),
     "kd": kw.get("keyword_difficulty", 0),
     "best_url": kw.get("best_position_url")}
    for kw in ahrefs_resp["keywords"]
]

candidates = []
candidates.extend(ahrefs_discover(competitor, {"keywords": translated}, inv))
candidates.extend(gsc_discover(gsc_resp, inv))
if ga4_rows is not None:
    candidates.extend(ga4_discover(ga4_rows, inv))
candidates.extend(searchable_discover(searchable_resp, inv))

# Cannibalization filter
clear = [
    c for c in candidates
    if evaluate(
        ProposedTopic(
            focus_keyword=c.focus_keyword,
            working_title=c.working_title,
            audience=c.audience,
            category_id=c.category_id,
        ),
        inv,
    ).severity not in ("critical", "high")
]

top = pick_top_candidate(clear)
if top is None:
    clickup_create_task_comment(
        task_id=CONTENT_PIPELINE_STATUS_TASK_ID,
        comment_text=f"Daily idea {today}: no clear candidates after cannibalization (out of {len(candidates)} raw).",
    )
    sys.exit(0)
```

### 6. Generate working title + outline

Generate (Claude, in the /loop context):
- working_title (≤120 chars, no trailing period, no em dashes, no "free audit")
- One-line angle (the differentiated take)
- Three H2-starter outline bullets

### 7. Persist state + emit ClickUp task

```python
proposal = candidate_to_proposal_dict(
    top, title=<working_title>, angle=<angle>, outline=<outline>, target_date=today,
)
state = DailyState(date=today, proposal=proposal)
save_state(state)

Skill(skill="fm-clickup-ops")

resp = clickup_create_task(
    list_id=CONTENT_PROJECTS_LIST_ID,
    name=f"[{today}] {proposal['working_title']}",
    markdown_description=<rich block with focus_kw, audience, evidence, top SERP results>,
    assignees=[APPROVER_CLICKUP_USER_ID],
    due_date=today,
    tags=["fm-content-daily"],
)
state = mark_emitted(state, task_id=resp.get("task_id") or resp.get("id"))
save_state(state)
```

### 8. Status comment + commit

```python
clickup_create_task_comment(
    task_id=CONTENT_PIPELINE_STATUS_TASK_ID,
    comment_text=(
        f"Daily idea {today}: emitted '{proposal['working_title']}' "
        f"from {top.discovery_source} (task {state.clickup_task_id})."
    ),
)
import subprocess
subprocess.run(["git", "add", "data/runs/_daily/"], check=False)
subprocess.run(["git", "commit", "-m", f"chore(daily): {today} state"], check=False)
subprocess.run(["git", "push"], check=False)
```

## Hard rules

- `status=draft` only (enforced at draft phase)
- No "free audit" in title or angle
- No em dashes
- No trailing period in title
- Audience routing: DFY → /consulting/, DIY → /labs/
- Cannibalization critical/high = hard block

## Failure handling

- Any single discovery source failing: log + continue with remaining sources (do not abort the run)
- All 4 sources failing: comment failure on the pipeline-status task (`CONTENT_PIPELINE_STATUS_TASK_ID`), exit non-zero, /loop retries next interval
- Inventory stale: comment + exit non-zero (operator refreshes manually)
- Cannibalization gate refuses to run on degraded entries: same as above

## Idempotency

- Local state file `data/runs/_daily/<TODAY>.json` is the primary lock
- ClickUp tag search (step 1a) is the secondary lock for dual-mode safety
- Both checks are no-ops once the legacy /schedule routines are disabled
