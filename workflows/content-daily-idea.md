# Daily idea (test-phase replacement for Sunday slate)

> **Goal.** Once per day at 07:00 Phoenix, post ONE blog title to ClickUp for Nikki to approve. The polling drafter (every 3h) picks up approvals automatically.

> **Cron.** `0 14 * * *` UTC (07:00 America/Phoenix, fixed offset UTC-7 year-round).

> **Test-phase only.** This replaces the weekly Sunday/Wednesday cycle. Run for ~2 weeks, then switch to weekly mode (`workflows/content-sunday-slate.md`).

---

## Inputs

- Today's date (UTC and Phoenix can both work; the state file is keyed by Phoenix date for consistency with other operators)
- Inventory snapshot at `data/inventory/firstmovers-ai.json` — must be fresh (≤7 days old)

If the inventory is stale, refresh first per `workflows/content-inventory-refresh.md`.

---

## Step-by-step

### 1. Verify environment

```python
import sys
sys.path.insert(0, ".")
from tools.daily import DAILY_DIR, load_state
from tools.inventory import load
from tools.inventory_refresh import freshness_check

assert freshness_check() == 0, "inventory stale — refresh first"
```

If today's state file already exists at `data/runs/_daily/<YYYY-MM-DD>.json`, **skip generation** and post a status comment "already emitted today" to the pipeline status task `86ah3ywyh`. Idempotent — no double-emit.

### 2. Pull discovery signals

> **v1 testing-phase note:** GSC striking-distance is disabled because there is no claude.ai built-in connector for Google Search Console (verified 2026-05-09). The daily routine runs on Ahrefs gap alone. Once we add a GSC SDK bypass module (see `tools/ga4.py` for the pattern) or claude.ai ships a GSC connector, re-enable the GSC source.

For v1 testing, only run the Ahrefs gap call (rotate competitors across days to keep API costs down):

| Day-of-week | Competitor (Ahrefs `target`) |
|---|---|
| Monday | mckinsey.com |
| Tuesday | bcg.com |
| Wednesday | bain.com |
| Thursday | hubspot.com |
| Friday | accenture.com |
| Saturday | deloitte.com |
| Sunday | mckinsey.com (fresh signal for the start of the week) |

```
mcp__ahrefs__site-explorer-organic-keywords(
  target="<competitor.com>",
  mode="subdomains",
  date="<today YYYY-MM-DD>",
  select="keyword,best_position,best_position_url,sum_traffic,volume,keyword_difficulty",
  limit=100,
  order_by="sum_traffic:desc"
)
```

### 3. Run discovery + cannibalization + pick top-1

```python
from tools.daily import (
    candidate_to_proposal_dict, mark_emitted,
    pick_top_candidate, save_state, DailyState,
)
from tools.discover.ahrefs_gap import discover as ahrefs_discover
from tools.discover.gsc import discover as gsc_discover
from tools.cannibalization import ProposedTopic, evaluate
from tools.inventory import load as load_inventory

inv = load_inventory()
inv.assert_fresh()
inv.assert_complete()

gsc_cands = gsc_discover(gsc_response, inv)
ahrefs_cands = []
for competitor in [<today's competitor>]:
    translated = [
        {"keyword": kw["keyword"], "volume": kw["volume"],
         "difficulty": kw["keyword_difficulty"], "position": kw["best_position"],
         "traffic": kw["sum_traffic"]}
        for kw in ahrefs_response.get("keywords", [])
    ]
    ahrefs_cands.extend(ahrefs_discover(competitor, {"keywords": translated}, inv))

all_cands = gsc_cands + ahrefs_cands

# Filter survivors past the cannibalization gate
clear_cands = []
for cand in all_cands:
    topic = ProposedTopic(
        slug=cand.focus_keyword.replace(" ", "-").lower(),
        title=cand.suggested_title_seed,
        focus_keyword=cand.focus_keyword,
        category_id=cand.category_id,
        audience=cand.audience,
    )
    verdict = evaluate(topic, inv)
    if verdict.severity not in ("critical", "high"):
        clear_cands.append(cand)

top = pick_top_candidate(clear_cands)
if top is None:
    # No safe candidates today — comment the pipeline status task and exit.
    # The next Sunday refresh / inventory rebuild may surface new ones.
    return
```

### 4. Generate title + angle + outline (LLM, ~50 tokens)

Compose a working title (≤120 chars, no trailing period, no em dashes), one-line angle, and three H2-starter outline bullets. Same shape as `slate.HAND_CRAFTED` entries.

### 5. Persist daily state

```python
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.now(ZoneInfo("America/Phoenix")).strftime("%Y-%m-%d")
proposal = candidate_to_proposal_dict(
    top, title=<generated_title>, angle=<generated_angle>,
    outline=<generated_outline>, target_date=today,
)
state = DailyState(date=today, proposal=proposal)
save_state(state)
```

### 6. Emit single ClickUp task (no parent — top-level)

> **v1 testing-phase note:** The claude.ai ClickUp connector is unavailable to `/schedule` remote routines (verified 2026-05-12 — the connector_uuid attached at registration becomes invalid when ClickUp reconnects). Use the direct REST wrapper `tools.clickup.create_task` instead. Requires `CLICKUP_API_TOKEN` env var (personal token starting with `pk_`).

```python
from tools.clickup import create_task, create_task_comment, add_tag_to_task

resp = create_task(
    list_id="901326229295",  # CONTENT_PROJECTS_LIST_ID
    name=f"[{today}] {proposal['working_title']}",
    markdown_description=<rich description with focus_kw, audience, category, outline, evidence>,
    assignees=[26221739],     # Nikki (int, not str)
    due_date=today,           # YYYY-MM-DD, internally converted to epoch-ms
    tags=["fm-content-daily"],
)
state = mark_emitted(state, task_id=resp["id"])   # NOTE: direct API returns "id", not "task_id"
save_state(state)
```

The task description should match the subtask format from `clickup.build_subtask_payloads` (focus_keyword, audience, category, intent, target_date, angle, outline bullets, discovery evidence).

### 7. Status comment on pipeline status task

```python
create_task_comment(
    task_id="86ah3ywyh",
    comment_text=(
        f"Daily idea {today} emitted: {proposal['working_title']!r} "
        f"(focus_kw: {proposal['focus_keyword']}, "
        f"score: {proposal['score']:.2f}, "
        f"source: {proposal['discovery_source']}). "
        f"ClickUp task: https://app.clickup.com/t/{resp['id']}"
    ),
)
```

---

## Edge cases

- **Stale inventory.** Refresh first; if refresh fails, skip today and post failure comment.
- **All candidates blocked.** Empty after cannibalization filter — happens when discovery surfaces only known topics. Post status comment, no ClickUp task. Try again tomorrow with a different rotated competitor.
- **Already emitted today.** State file exists — skip silently. Idempotent guard against double-cron firing.

## Failure modes that page

- `StaleInventoryError` AND inventory refresh failed
- ClickUp `create_task` 4xx/5xx → retry once, then comment + page
- All discovery sources returned 0 candidates for 3 consecutive days → likely a real signal regression
