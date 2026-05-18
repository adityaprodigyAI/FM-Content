# Heartbeat canary — /schedule safety net

> **Goal.** If the VPS jobs are not firing (VPS down, cron broken, or the Claude login expired), this /schedule routine still fires from claude.ai cloud — independently of the VPS — and pings the ClickUp pipeline status task. The operator notices and fixes whatever needs fixing.

> **Templating.** This routine runs in the claude.ai cloud sandbox — it has NO access to the repo, so it cannot read `client_config.toml`. The two ClickUp ids below appear as `<<PLACEHOLDERS>>`. Before running `/schedule create`, substitute them with the client's real values from `client_config.toml`:
> - `<<CONTENT_PROJECTS_LIST_ID>>` ← `clickup.content_projects_list_id`
> - `<<PIPELINE_STATUS_TASK_ID>>` ← `clickup.pipeline_status_task_id`

> **Cron.** `0 */12 * * *` UTC (every 12 hours: 00:00 and 12:00 UTC).

> **Why.** The daily-idea and polling-drafter jobs run as system cron on the VPS. If the VPS goes down or a job silently breaks, no errors surface anywhere. This heartbeat runs in the claude.ai cloud, completely independent of the VPS, so it is the one thing that can still raise the alarm.

---

## What it does

Minimal, no local-MCP dependencies. Only needs the ClickUp claude.ai connector.

1. List the most recent task tagged `fm-content-daily` in the Content Projects list (`<<CONTENT_PROJECTS_LIST_ID>>`)
2. Compute time-since-last-emit
3. If > 36h since last emit → ALERT on the pipeline-status task (`<<PIPELINE_STATUS_TASK_ID>>`) (both fires)
4. If healthy AND this is the 00:00 UTC fire → post a daily "ok" tick
5. If healthy AND this is the 12:00 UTC fire → silent (keep the canary task clean)

The morning ok-tick is the positive proof-of-life signal so smoke tests and post-deploy verification can confirm the routine actually ran.

## Routine prompt (paste into `/schedule create`)

```text
FM-Content heartbeat canary routine. Runs every 12 hours UTC. Full SOP: workflows/heartbeat-canary.md.

Setup: this routine uses the attached ClickUp MCP connector ONLY. No local filesystem actions, no GSC, no Ahrefs, no GA4. Do NOT call api.clickup.com directly — the routine sandbox blocks outbound HTTP to non-allowlisted hosts. The attached ClickUp connector is the only network path.

WORKFLOW:

1. List the single most recent task tagged 'fm-content-daily' in the Content Projects list via the attached ClickUp MCP:
     resp = clickup_search(list_id='<<CONTENT_PROJECTS_LIST_ID>>', tags=['fm-content-daily'], order_by='created', reverse=True, limit=1)

2. If resp has no tasks at all, ALERT and exit:
     clickup_create_task_comment(task_id='<<PIPELINE_STATUS_TASK_ID>>', comment_text='Heartbeat ALERT: no daily-idea tasks found in the recent window. The VPS may be offline or the daily-idea job has been broken for >1 week.')
     exit 0

3. Otherwise, compute hours since the latest task's date_created (ClickUp returns it as ms since epoch as a string):
     from datetime import datetime, timezone
     latest = resp['tasks'][0]
     created_at = datetime.fromtimestamp(int(latest['date_created']) / 1000, tz=timezone.utc)
     now = datetime.now(timezone.utc)
     hours_since = (now - created_at).total_seconds() / 3600

4. If hours_since > 36, ALERT regardless of fire hour:
     clickup_create_task_comment(task_id='<<PIPELINE_STATUS_TASK_ID>>', comment_text=f'Heartbeat ALERT: last daily-idea task was {hours_since:.1f} hours ago. Expected fresh task every 24h. The VPS may be down or cron may have stopped — SSH into the VPS and check.')
     exit 0

5. Otherwise (healthy), check the current UTC hour:
     if now.hour < 6:
         # Morning fire (00:00 UTC ± jitter) — post the daily ok tick
         clickup_create_task_comment(task_id='<<PIPELINE_STATUS_TASK_ID>>', comment_text=f'Heartbeat ok: last daily-idea task {hours_since:.1f}h ago. Pipeline alive.')
     # else: the 12:00 UTC fire stays silent

That is the entire routine. No other actions.
```

## MCP connections required

- The client's ClickUp claude.ai connector. The connector UUID is per-client —
  pick the client's ClickUp connector in the `/schedule create` UI. (For the
  First Movers reference install it is `37a27fca-ed4a-4ab5-af86-7448fc489f8d`.)

## Registration

```
/schedule create
  name=fm-content-heartbeat
  cron="0 */12 * * *"
  model=claude-sonnet-4-6
  prompt=<contents of "Routine prompt" section above>
  mcp_connections=[ClickUp]
```

## Failure handling

This routine is intentionally minimal. If even this fails, investigate the ClickUp connector itself.

## When to retire

Never — keep it. The jobs now run on an always-on VPS, but the VPS can still fail (downtime, an expired Claude login, a broken cron). This heartbeat is the only thing that pages independently of the VPS, so it stays.
