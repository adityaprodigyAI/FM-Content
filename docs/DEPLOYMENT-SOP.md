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

A two-job content engine that produces WordPress blog drafts:

| Job | Cadence | What it does |
|---|---|---|
| **daily-idea** | once/day | Pulls 4 discovery sources (Ahrefs gap, GSC striking-distance, GA4 decay, Searchable AEO) → runs the cannibalization gate → posts ONE topic to ClickUp for the client's approver. |
| **polling-drafter** | every 3h | Detects approved ClickUp tasks → fetches SERP → generates rubric-compliant prose → pushes a WordPress **draft** (never publishes). |
| **heartbeat** | every 12h | A `/schedule` cloud canary. Alerts on the ClickUp status task if no daily-idea task has appeared in 36h. |

Both jobs run as `/loop`s inside the operator's local Claude Code session. The
heartbeat runs in the claude.ai cloud as a `/schedule` routine — it is the
safety net for when the operator's machine is closed.

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
- `[schedule]` — `operator_timezone` (the timezone of the machine running
  `/loop`), the two `/loop` cron expressions **in operator-local time**, and
  `content_timezone` (the timezone state files are keyed by).
- `[rubric]` — `skill_name`: the name of this client's blog-rubric skill
  directory under `.claude/skills/`.

> **Timezone gotcha.** `CronCreate` (the engine behind `/loop`) interprets cron
> expressions in the operator's **local** timezone, not UTC. Compute the cron so
> the job fires at the desired hour in the *content* timezone, expressed in
> *operator-local* time. Example: First Movers wants 07:00 America/Phoenix; the
> operator is in Asia/Kolkata; 07:00 Phoenix = 19:33 IST → `33 19 * * *`.

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

### Step 6 — Verify (see §4), then register the loops (see §5).

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

## 5. Running the loops

Inside the operator's Claude Code session, register both `/loop`s using the
cron expressions from `client_config.toml` → `[schedule]`:

- daily-idea: `schedule.daily_idea_local_cron`, prompt = the daily-idea loop
  workflow (`workflows/content-daily-idea-loop.md`).
- polling-drafter: `schedule.polling_drafter_local_cron`, prompt = the
  poll-and-draft loop workflow (`workflows/content-poll-and-draft-loop.md`).

Then register the heartbeat as a `/schedule` cloud routine following
`workflows/heartbeat-canary.md` — remember to substitute the two
`<<PLACEHOLDER>>` ClickUp ids with the client's real values before pasting.

> **`/loop` is session-bound.** It fires only while the operator's Claude Code
> is open. When the session closes, the loops stop; the heartbeat catches the
> gap. Re-register both loops at the start of every session. Moving the loops to
> an always-on VM is a separate future project.

---

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `FileNotFoundError: client_config.toml not found` | The config file is missing or the repo layout changed. It must sit at the repo root. |
| WP push rejected / 403 | WAF block. Drafts queue to `data/runs/_pending-push/`; push from outside the WAF via the `wp-push-fallback` GitHub Action. |
| `StaleInventoryError` | Inventory > 7 days old. Re-run `python -m tools.inventory_refresh`. |
| Cannibalization gate refuses to run | Inventory is degraded (a post is missing `focus_keyword` or `organic_keywords`). Rebuild the inventory. |
| daily-idea task lands in the wrong ClickUp list | `clickup.content_projects_list_id` is wrong in the config. |
| `/loop` never fired overnight | Expected — `/loop` is session-bound. Re-register at session start; the heartbeat should have alerted. |
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
