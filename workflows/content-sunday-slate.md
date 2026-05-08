# Sunday slate job (Phase 0a)

> **Goal.** By Sunday 07:00 Phoenix, post a 12-row title slate to ClickUp. Nikki ticks ≤7 by Tuesday EOD.

> **Schedule.** Cron `0 14 * * 0 UTC` (Sun 07:00 America/Phoenix; Phoenix is fixed offset UTC-7 year-round, no DST).

This is the agent contract. Run as a `/schedule` agent. Touches no prose — the prose is generated Wednesday for only the titles Nikki approves.

---

## Inputs

- Current week, e.g. `2026-W22` (`datetime.now(ZoneInfo("America/Phoenix")).strftime("%G-W%V")`).
- Inventory snapshot at `data/inventory/firstmovers-ai.json` (must be ≤ 7 days old).

If the inventory snapshot is stale, refresh it first (see `workflows/content-inventory-refresh.md`). Fail loud if you can't refresh — never run the slate on stale data.

---

## Step-by-step

### 1. Verify environment

```python
import sys
sys.path.insert(0, ".")  # so `tools.*` imports work
from tools.inventory_refresh import freshness_check
assert freshness_check() == 0, "inventory is stale or missing — refresh first"
```

If freshness_check returns 1 or 2, run `workflows/content-inventory-refresh.md`.

### 2. Load the inventory

```python
from tools.inventory import load
inventory = load()
inventory.assert_fresh()
inventory.assert_complete()
inventory.assert_pages_present(min_pages=5)
```

If `assert_complete` raises, the snapshot has missing focus_keyword or organic_keywords — DO NOT proceed. Refresh inventory.

### 3. Pull discovery signals (4 MCP calls)

#### 3a. GSC striking-distance

```
mcp__gsc__get_search_analytics(
  siteUrl="https://firstmovers.ai/",
  start_date=<28 days ago>,
  end_date=<yesterday>,
  dimensions=["query","page"],
  rowLimit=200
)
```

Pass the response straight into:

```python
from tools.discover.gsc import discover as gsc_discover
gsc_candidates = gsc_discover(gsc_response, inventory)
```

This drops queries whose ranking URL is already a known FirstMovers URL — the W20 fix at the discovery layer.

#### 3b. Ahrefs competitor gap

For each competitor in `tools.identities.GAP_DISCOVERY_COMPETITORS`:

```
mcp__ahrefs__site-explorer-organic-keywords(
  target=<competitor>,           # e.g. "mckinsey.com"
  limit=200,
  order_by="organic_traffic:desc"
)
```

Pass each response in:

```python
from tools.discover.ahrefs_gap import discover as ahrefs_discover
from tools.identities import GAP_DISCOVERY_COMPETITORS

ahrefs_candidates = []
for competitor in GAP_DISCOVERY_COMPETITORS:
    ahrefs_candidates += ahrefs_discover(competitor, response_for_competitor[competitor], inventory)
```

#### 3c. Searchable AEO

> **v1.1 status:** the `mcp__claude_ai_searchable__*` server has not been
> successfully invoked from FM-Content (no log directory created on first
> attempt; the calls hung). Skip this source for now and let the operator
> reconnect Searchable via `claude mcp` before the next Sunday cron.

```
mcp__claude_ai_searchable__get_visibility_by_prompt(projectId="a04206b9-89ae-4175-8d4d-af48af32a1c6")
mcp__claude_ai_searchable__get_visibility_by_topic(projectId="a04206b9-89ae-4175-8d4d-af48af32a1c6")
```

Pass responses in:

```python
from tools.discover.searchable_aeo import discover_prompts, discover_topics
prompt_candidates = discover_prompts(prompt_response, inventory)
topic_candidates = discover_topics(topic_response, inventory)
```

#### 3d. GA4 high-traffic gap

**Do not use `mcp__analytics-mcp__*`** — that server hangs indefinitely (verified 2026-04-27 and 2026-05-08). Use the direct SDK bypass instead:

```python
from tools.ga4 import fetch_high_traffic_with_growth
from tools.discover.ga4_gap import discover as ga4_discover

# Requires GOOGLE_APPLICATION_CREDENTIALS env var pointing at a service-account
# JSON, OR ADC creds at ~/AppData/Roaming/gcloud/application_default_credentials.json
# (see tools/ga4.py docstring for setup).
rows = fetch_high_traffic_with_growth(window_days=28, limit=50)
ga4_candidates = ga4_discover(rows, inventory)
```

Verify auth works first with `python -m tools.ga4 --check` (read-only). Install the SDK with `pip install -e ".[ga4]"`.

### 4. Build the slate

```python
from tools.slate import build_slate

# 4a. Optional: generate a custom working_title + angle + 3 outline bullets
# per candidate (~50 LLM tokens × 12 = 600 tokens). Keys are focus_keyword.
titles_by_focus_kw = {
    cand.focus_keyword: {
        "title": "<Claude-generated title, ≤120 chars, no trailing period, no em dashes>",
        "angle": "<one-line angle>",
        "outline": ["<H2 starter 1>", "<H2 starter 2>", "<H2 starter 3>"],
    }
    for cand in (
        gsc_candidates + ahrefs_candidates + prompt_candidates +
        topic_candidates + ga4_candidates
    )[:30]  # only generate for the top 30 — slate caps at 12 anyway
}

slate = build_slate(
    week="2026-W22",
    candidates=(gsc_candidates + ahrefs_candidates +
                prompt_candidates + topic_candidates + ga4_candidates),
    inventory=inventory,
    titles_by_focus_kw=titles_by_focus_kw,
)
```

`build_slate` handles dedupe, cannibalization filtering (drops critical + high), source-weighted ranking, and target-date assignment.

### 5. Persist + post

```python
from tools.slate import write_slate
slate_path = write_slate(slate)
print(f"Slate written to {slate_path}")
```

Then post to ClickUp:

```python
from tools.clickup import build_parent_task_payload, build_subtask_payloads, build_status_comment

parent_payload = build_parent_task_payload(slate)
parent = mcp__claude_ai_ClickUp__clickup_create_task(
    list_id=parent_payload.list_id,
    name=parent_payload.name,
    description=parent_payload.description,
    assignees=parent_payload.assignees,
)
parent_id = parent["id"]

for sub in build_subtask_payloads(slate, parent_task_id=parent_id):
    mcp__claude_ai_ClickUp__clickup_create_task(
        list_id=parent_payload.list_id,
        parent=sub.parent_task_id,
        name=sub.name,
        description=sub.description,
        assignees=sub.assignees,
        custom_id=sub.custom_id,
    )

# Status comment on the long-running pipeline status task
mcp__claude_ai_ClickUp__clickup_create_task_comment(
    task_id="86ah3ywyh",
    comment_text=build_status_comment(slate, parent_id),
)
```

### 6. Done

The Sunday job is finished. Nikki sees the slate in her ClickUp inbox. The Wednesday job (`workflows/content-wednesday-draft.md`) reads her approvals.

---

## Edge cases

- **All 12 weak.** Nikki may approve 0. The Wednesday job runs anyway, finds 0 approvals, posts a status comment, and exits. The unapproved titles roll back into next Sunday's candidate pool.
- **Inventory refresh failed.** The Sunday job MUST NOT run. Post a status comment to `86ah3ywyh` describing the failure. Page Aditya.
- **Cron drift.** If the Sunday job fires and Nikki hasn't acted on the previous slate, that's fine — the new slate is in a new ClickUp task, the old one stays around for archival. Each task is per-week.

## Failure modes that page

- `StaleInventoryError` from `assert_fresh` — refresh failed.
- `DegradedInventoryError` from `assert_complete` — refresh produced a snapshot with missing focus_keyword or organic_keywords. The cannibalization gate refused to run.
- `CannibalizationError` raised — should never happen; the slate builder filters before raising. If it does, file a bug.
- `clickup_create_task` 4xx/5xx — pause and retry once, then page Aditya.
