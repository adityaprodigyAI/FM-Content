# Weekly VPS health report

> **Goal.** Every Monday morning, run a comprehensive health check on the VPS
> and post the result as a single markdown comment on the ClickUp pipeline-
> status task `86ah3ywyh`. Provides positive weekly proof-of-life and surfaces
> anomalies the existing 12-hour heartbeat can't catch (e.g. one job failing
> repeatedly while the daily-idea pipeline as a whole still emits — the
> heartbeat would stay quiet but this report would not).

> **Runtime.** Executed by the weekly health-report cron job on the VPS
> (`~/fm-content/scripts/run-job.sh workflows/health-report.md health-report`)
> every Monday at 08:00 Phoenix.

---

## What to check

Use the Bash tool to gather. Then build ONE markdown report covering each of
the following sections, with a per-section ✅ / ⚠️ / ❌ marker:

1. **Host** — uptime, system timezone, memory used/total, disk %.
   (`uptime -p`, `timedatectl show -p Timezone --value`, `free -h`, `df -h /`)
2. **Services** — `cron`, `fail2ban`, `ufw` all active.
   (`systemctl is-active <service>` and `sudo ufw status | head -1`)
3. **Cron pipeline** — `crontab -l | grep -v '^#'` lists the expected jobs.
   For each job (daily-idea, polling-drafter, inventory-refresh, health-report):
   the latest START timestamp from `~/fm-content/logs/<job>.log`, the count of
   STARTs in the past 7 days (also scan rotated `*.log.1` and `*.log.*.gz`), and
   any `(exit [1-9])` failures in the past 7 days. Flag any missing END marker
   that's older than ~2 hours (stuck or killed run).
4. **Git** — `git -C ~/fm-content fetch origin --quiet && git status -sb` shows
   a clean tree in sync with `origin/main`. `git log --oneline -5` for the
   latest activity.
5. **State files** — count of `data/runs/_daily/YYYY-MM-DD.json` files for the
   past 7 days. Flag any missing day and check the corresponding daily-idea log
   to see whether daily-idea refused to emit (legitimate) or simply didn't fire.
6. **Inventory** — `python -m tools.inventory_refresh --check` reports `fresh`.
   Print entry count and the blogs/pages breakdown plus `generated_at` (UTC).
7. **MCP servers** — `claude mcp list` shows ✓ Connected for the 5 the pipeline
   relies on: `claude.ai Ahrefs`, `claude.ai ClickUp`, `claude.ai searchable`,
   `claude.ai FirstMoversWP`, and the local `gsc` stdio server.

## Output format

A single markdown comment, sections in the order above, each with a status
marker on its own line. End with an explicit verdict on its own line:

- `**OVERALL: HEALTHY** — everything operating as expected.`
- `**OVERALL: NEEDS ATTENTION** — <concise list of issues>.`

If the verdict is **NEEDS ATTENTION**, include a final "What to check" block
naming the file path or log line the operator should look at.

## How to post

Call the claude.ai ClickUp connector tool ONCE to post the comment, then exit:

```
clickup_create_task_comment(
    task_id="86ah3ywyh",
    comment_text=<the full markdown report from above>,
)
```

No commits. No state file writes. No other ClickUp actions. Just the one
comment, then exit.
