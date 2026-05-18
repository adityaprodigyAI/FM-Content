# Onboarding — FM-Content Pipeline

Welcome. This repo is a **reusable content-automation pipeline**: it discovers
blog topics, blocks cannibalization, writes rubric-compliant prose, and pushes
WordPress drafts for a human to review and publish. It ships configured for
First Movers (`firstmovers.ai`) as the reference implementation, and is built to
be retargeted to any client by editing **one config file**.

## What this pipeline does

Two automated jobs plus a safety net:

- **daily-idea** (once/day) — pulls 4 discovery sources (Ahrefs competitor gap,
  Google Search Console striking-distance, GA4 traffic decay, Searchable AEO),
  runs the cannibalization gate, and posts ONE topic to ClickUp for the client's
  approver.
- **polling-drafter** (every 3h) — when the approver marks a task done,
  generates a full draft (SERP-researched, rubric-validated) and pushes it to
  WordPress as `status=draft`. A human always publishes.
- **heartbeat** (every 12h, cloud) — alerts in ClickUp if daily-idea has not run
  in 36h.

The non-negotiable rule: the cannibalization gate never lets a topic overlap
something the client has already published.

## Who are you? Pick your path

### → You are setting this up for a NEW client

Read **[docs/DEPLOYMENT-SOP.md](docs/DEPLOYMENT-SOP.md)**. It is the complete
new-client onboarding walkthrough. The short version:

1. Edit `client_config.toml` — the single per-client config file. Every id,
   URL, timezone, and competitor lives here.
2. Copy `.env.example` → `.env` and fill in the secrets (WordPress app
   password, Ahrefs token, GA4 service-account path).
3. Supply three content files: `tools/external_links.py` (citation allowlist),
   `tools/internal_links.py` (the client's own links), and a
   `.claude/skills/<client>-blog-rubric/SKILL.md` (brand voice).
4. Connect the client's MCPs (WordPress, Ahrefs, GSC, Searchable, ClickUp).
5. Build the first inventory snapshot, verify, and deploy to an always-on VPS
   (system cron runs the jobs — see DEPLOYMENT-SOP §5).

You do **not** edit any other Python file. The whole `tools/` package reads
client-specific values through `tools/identities.py`, which loads
`client_config.toml`.

### → You are OPERATING an already-configured install

Read **[docs/SYSTEM-HANDOVER.md](docs/SYSTEM-HANDOVER.md)** — day-to-day
operation, the session-reopen recovery playbook, and the incident history.

Key things to know:

- The jobs run as **system cron on an always-on VPS** — they fire 24/7 with no
  laptop and no re-registration. The VPS crontab is the schedule.
- The `/schedule` heartbeat is the independent cloud canary if the VPS goes down.
- Job logs live on the VPS at `~/fm-content/logs/*.log`.
- Project rules and the MCP map are in [CLAUDE.md](CLAUDE.md).

## Repo map

| Path | What it is |
|---|---|
| `client_config.toml` | **The single per-client config file.** Start here. |
| `.env.example` | Template for the secrets file. |
| `tools/` | The pipeline engine — discovery, cannibalization, rubric, push. |
| `tools/identities.py` | Loads `client_config.toml`; the bridge between config and code. |
| `workflows/` | The job SOPs the cron jobs execute. |
| `.claude/skills/` | The 8 process skills + the client's blog-rubric skill. |
| `docs/DEPLOYMENT-SOP.md` | New-client onboarding walkthrough. |
| `docs/SYSTEM-HANDOVER.md` | Day-to-day operations + incident playbook. |
| `tests/` | The regression suite (`python -m pytest tests/`). |

## Quick health check

```
python -c "import tools.identities; print('config OK')"
python -m pytest tests/
```

Both should pass before you trust an install.
