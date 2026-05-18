# Deployment SOP — Onboarding a New Client

> **Audience.** The agency operator standing up this content-automation pipeline
> for a *new* client. The reference implementation in this repo is First Movers
> (`firstmovers.ai`). This SOP explains how to retarget the whole pipeline to a
> different brand.

> **Design promise.** All client-specific values live in **one file** —
> `client_config.toml`. You should never edit a `.py` file in `tools/` to
> onboard a client. You edit config, connect MCPs, populate `.env`, and supply
> three content files (citations, internal links, brand-voice rubric).

---

## 1. What the pipeline does

A three-job content engine that produces WordPress blog drafts:

| Job | Cadence | What it does |
|---|---|---|
| **daily-idea** | once/day | Pulls 4 discovery sources (Ahrefs gap, GSC striking-distance, GA4 decay, Searchable AEO) → runs the cannibalization gate → posts ONE topic to ClickUp for the client's approver. |
| **polling-drafter** | every 3h | Detects approved ClickUp tasks → fetches SERP → generates rubric-compliant prose → pushes a WordPress **draft** (never publishes). |
| **inventory-refresh** | weekly | Rebuilds the published-content inventory snapshot the cannibalization gate compares against. |
| **heartbeat** | every 12h | A `/schedule` cloud canary. Alerts on the ClickUp status task if no daily-idea task has appeared in 36h. |

The three jobs run as **system cron** on an always-on VPS — headless `claude -p`
fires each on schedule, 24/7, surviving reboots (see §5). The heartbeat runs in
the claude.ai cloud as a `/schedule` routine — the independent canary for if the
VPS itself goes down.

The single most important guarantee: the **cannibalization gate**
(`tools/cannibalization.py`) blocks any topic that overlaps something the client
has already published. Never weaken, bypass, or run it on stale inventory.

---

## 2. The files you edit per client

| # | File | What goes in it |
|---|---|---|
| 1 | `client_config.toml` | Every per-client id, URL, timezone, competitor list. The single source of truth. |
| 2 | `.env` | Secrets only — WP app password, Ahrefs token, GA4 service-account path. Copy from `.env.example`. Gitignored. |
| 3 | `tools/external_links.py` | The curated outbound-citation allowlist, per blog category. Brand-appropriate authoritative sources. |
| 4 | `tools/internal_links.py` | The client's own Tier-1 landing pages and cross-link blog URLs. |
| 5 | `.claude/skills/<client>-blog-rubric/SKILL.md` | The client's brand voice, profile stats, power words, forbidden phrases. |

Files 3 and 4 are *content* files — they happen to be Python, but you are only
editing data lists, not logic. File 5 is a Claude skill.

**You never touch:** anything else in `tools/`, the workflow SOPs, or the test
suite. They read everything client-specific through `tools/identities.py`, which
loads `client_config.toml`.

---

## 3. Step-by-step onboarding

### Step 0 — Fork the repo for the client

Clone this repo into a fresh per-client directory (or a new private git repo).
Keep one repo per client — state files (`data/runs/`, `data/inventory/`) are
client-specific and must not mix.

### Step 1 — Fill in `client_config.toml`

Open `client_config.toml` and replace every value. Each key is documented
inline. The sections:

- `[brand]` — name, `site_base_url`, `site_host`.
- `[wordpress]` — `author_id` (the WP user every draft is authored under) and
  `category_ids` (the valid blog categories — the rubric rejects any other).
  Get the author id from `GET /wp-json/wp/v2/users`; category ids from
  `GET /wp-json/wp/v2/categories?per_page=100`.
- `[clickup]` — `workspace_id`, `content_projects_list_id` (where daily-idea
  tasks land), `pipeline_status_task_id` (the canary task), `approver_user_id`
  and `approver_name` (who approves), optional `cta_approver_user_id` /
  `cta_approver_name`.
- `[searchable]`, `[ga4]`, `[gsc]` — the AEO / analytics / search-console
  targets. Leave any `project_id` / `property_id` / `site_url` as `""` to
  disable that discovery source (the pipeline degrades gracefully).
- `[discovery]` — `competitor_rotation` (one competitor domain per weekday,
  Monday→Sunday) and `kd_ceiling` (skip keywords harder than this; tune to the
  client's domain rating).
- `[audience_routing]` — maps each audience tier to its CTA path. Keys must be
  exactly `"done-for-you"` and `"diy"`.
- `[schedule]` — `content_timezone` (the timezone state files are keyed by, and
  the timezone the VPS system clock is set to). The cron expressions in this
  section are informational; the VPS crontab is the actual timing authority
  (see §5).
- `[rubric]` — `skill_name`: the name of this client's blog-rubric skill
  directory under `.claude/skills/`.

> **Timezone tip.** Set the VPS system timezone to the client's
> `content_timezone` (`sudo timedatectl set-timezone ...`). Then the crontab
> times are direct — `0 7 * * *` simply means 07:00 for the client — with no
> UTC conversion to get wrong.

### Step 2 — Populate `.env`

Copy `.env.example` to `.env` and fill in secrets:

- `FM_WP_USER` / `FM_WP_APP_PASSWORD` — a WordPress Application Password
  (Users → Profile → Application Passwords). Not the login password.
- `FM_WP_AUTHOR_ID` — same value as `wordpress.author_id` in the config.
- `AHREFS_API_TOKEN` — only needed for the direct Ahrefs wrapper; optional if
  discovery always runs through the local Ahrefs MCP.
- `GOOGLE_APPLICATION_CREDENTIALS` — absolute path to a Google service-account
  JSON with the Analytics Data API enabled; add that service account as a
  Viewer on the GA4 property. Leave blank to disable GA4 discovery.

`.env` is gitignored. Never commit it.

### Step 3 — Supply the three content files

- **`tools/external_links.py`** — replace the curated citation allowlist with
  authoritative sources appropriate to the client's industry, keyed by their
  blog category ids.
- **`tools/internal_links.py`** — replace the Tier-1 landing page URLs and the
  cross-link blog URLs with the client's own. Keep the `audience` tags accurate
  (a `done-for-you` blog should cross-link to consulting-tier pages).
- **`.claude/skills/<client>-blog-rubric/SKILL.md`** — copy the
  `firstmovers-blog-rubric` skill directory to the name you set in
  `[rubric].skill_name`, then rewrite the brand voice, audience profile, power
  words, and forbidden phrases for the new client.

### Step 4 — Connect the MCPs

In the operator's Claude Code, connect the client's instances of:

| MCP | Used for |
|---|---|
| WordPress (`first-movers-wordpress`-equivalent) | Inventory build + draft push |
| Ahrefs (`ahrefs`) | Competitor-gap discovery + SERP intent |
| GSC (`gsc`) | Striking-distance discovery |
| Searchable (`claude_ai_searchable`) | AEO discovery |
| ClickUp (`first-movers-clickup`-equivalent) | Task emit + approval read |

GA4 does **not** use an MCP — `tools/ga4.py` calls the Google SDK directly
(`analytics-mcp` hangs; never use it). Airtable, n8n, and the Elementor MCPs are
**not** used by this pipeline.

### Step 5 — Build the first inventory snapshot

Run the inventory refresh so the cannibalization gate has data:

```
python -m tools.inventory_refresh
```

The snapshot lands at `data/inventory/<site-host>.json` (the filename is derived
from `brand.site_host`). It must be ≤7 days old or every draft run hard-fails.

### Step 6 — Verify (see §4), then deploy to the VPS (see §5).

---

## 4. Verification checklist

Run before going live. Every item must pass.

- [ ] `python -c "import tools.identities"` — no `FileNotFoundError` (config is
      present and parses).
- [ ] `python -m pytest tests/` — all tests green.
- [ ] `python -m tools.ahrefs check` — Ahrefs auth OK.
- [ ] `python -m tools.ga4 --help` runs; a real `run_report` returns rows (or
      GA4 is intentionally disabled with `property_id = ""`).
- [ ] Inventory snapshot exists at `data/inventory/<site-host>.json` and is
      fresh.
- [ ] Each of the 8 process skills loads: `Skill(skill="fm-ahrefs")` etc., plus
      the client's `<client>-blog-rubric`.
- [ ] A manual daily-idea run writes `data/runs/_daily/<today>.json` and creates
      a ClickUp task in the configured list, assigned to the approver.
- [ ] A manual polling-drafter run (after marking that task done) pushes a WP
      **draft** with the configured `post_author` and Rank Math meta populated.

---

## 5. Deploy to an always-on VPS

The pipeline runs as **system cron jobs on a small always-on Linux VPS**, so the
schedule fires 24/7 with no laptop, no `/loop`, and no re-registration. Stand
one up per client:

1. **Provision** a VPS (Hostinger KVM, ~2 vCPU / 4-8 GB RAM, Ubuntu 24.04 LTS).
   Harden it: a non-root user, key-only SSH (disable root login + password
   auth), `ufw` allowing only SSH, `fail2ban`. Set the system timezone to the
   client's content timezone (`sudo timedatectl set-timezone ...`) so cron
   expressions are direct, with no UTC conversion.
2. **Install the runtime:** Node.js LTS + Claude Code
   (`npm i -g @anthropic-ai/claude-code`), Python 3.10+, `git`, `gh`.
3. **Authenticate Claude Code** with the client's (or agency's) Claude
   subscription — run `claude` and complete `/login`.
4. **Clone the repo** using a GitHub deploy key *with write access* (the jobs
   commit state back). Build the venv:
   `python3 -m venv .venv && .venv/bin/pip install -e ".[ga4,dev]"`.
5. **Copy secrets:** `scp` `.env` and the GA4 service-account JSON to the VPS;
   `chmod 600` both; set `GOOGLE_APPLICATION_CREDENTIALS` to the VPS path. Quote
   any `.env` value containing spaces (e.g. the WordPress app password) so the
   wrapper can `source` the file.
6. **Connect the discovery sources** on the VPS: Ahrefs, ClickUp, and Searchable
   come through the operator's **claude.ai account connectors** automatically
   once Claude Code is logged in; **GSC** runs as a local `mcp-gsc` server
   (clone it, build its venv, authenticate with an OAuth token at
   `~/.config/mcp-gsc/token.json`); **GA4** needs no MCP — it uses the
   service-account JSON.
7. **Verify** on the VPS: run §4's checklist, then one manual `claude -p` run
   each of daily-idea and polling-drafter — confirm a ClickUp task and a
   WordPress draft are produced.
8. **Install the cron jobs.** Create the wrapper
   `~/fm-content/scripts/run-job.sh` (it `cd`s to the repo, sources `.env`,
   activates the venv, runs `claude -p` against the workflow file, logs to
   `~/fm-content/logs/`). Then a crontab — VPS timezone is the content timezone,
   so times are direct:
   ```cron
   0 7 * * *    run-job.sh workflows/content-daily-idea-loop.md     daily-idea        200
   0 */3 * * *  run-job.sh workflows/content-poll-and-draft-loop.md polling-drafter   400
   0 5 * * 1    run-job.sh workflows/content-inventory-refresh.md   inventory-refresh 200
   ```
9. **Register the heartbeat** as a `/schedule` cloud routine per
   `workflows/heartbeat-canary.md` (substitute the two `<<PLACEHOLDER>>` ClickUp
   ids). It is the independent canary if the VPS itself fails.
10. Add a `logrotate` rule for `~/fm-content/logs/*.log` (include an
    `su <user> <user>` directive), then reboot the VPS once to confirm cron
    resumes automatically.

The reference First Movers install runs on a Hostinger VPS at `187.77.146.79`
(Ubuntu 24.04, user `fmcontent`).

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `FileNotFoundError: client_config.toml not found` | The config file is missing or the repo layout changed. It must sit at the repo root. |
| WP push rejected / 403 | WAF block. Drafts queue to `data/runs/_pending-push/`; push from outside the WAF via the `wp-push-fallback` GitHub Action. |
| `StaleInventoryError` | Inventory > 7 days old. Re-run `python -m tools.inventory_refresh`. |
| Cannibalization gate refuses to run | Inventory is degraded (a post is missing `focus_keyword` or `organic_keywords`). Rebuild the inventory. |
| daily-idea task lands in the wrong ClickUp list | `clickup.content_projects_list_id` is wrong in the config. |
| Jobs stopped firing | On the VPS check: `crontab -l` lists the 3 jobs, `systemctl is-active cron`, and `claude -p "hi"` still works (the Claude subscription login can expire — re-run `claude` to re-login). The heartbeat should have alerted on the status task. |
| GA4 discovery silently skipped | `GOOGLE_APPLICATION_CREDENTIALS` unset/expired, or `ga4.property_id` is `""`. The pipeline continues on the other 3 sources by design. |

---

## 7. Hard rules (never change per client)

These are enforced in code and must hold for every client:

1. Drafts are created with `status=draft`. The pipeline never publishes.
2. Every draft is authored under the configured `wordpress.author_id`.
3. The cannibalization gate's critical/high severities are hard blocks.
4. Inventory snapshot must be ≤7 days old.
5. WordPress calls reject any host that is not the configured `site_host`.
6. Audience routing is never crossed (`done-for-you`→consulting,
   `diy`→labs/equivalent).

If `rubric.validate(draft)` raises, the message names the exact rule violated.
Fix the prose — never silence the validator.
