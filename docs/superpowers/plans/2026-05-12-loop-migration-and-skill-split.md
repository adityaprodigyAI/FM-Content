# Loop Migration + Skill Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Scope note (2026-05-12, revised during eng review):** This plan covers the workflow + /loop migration on the operator's **local Windows workstation**. VM provisioning is explicitly deferred to a separate future plan. The goal here is to prove the /loop runtime + new skill structure works end-to-end before investing in always-on infrastructure.

**Goal:** Migrate the two FM-Content `/schedule` routines (daily-idea, polling-drafter) to `/loop`s running in the operator's local Claude Code session on Windows, so the pipeline can use the GSC + GA4 + Searchable local MCPs that the `/schedule` sandbox proxy blocks. Simultaneously split the single monolithic `firstmovers-blog-rubric` skill into 8 process-specific skills for cleaner agent context loading.

**Architecture:** Hybrid runtime, local-first. Two `/loop`s run in the operator's local Claude Code session on Windows — daily-idea at 14:00 UTC (07:00 Phoenix), polling-drafter every 3 hours — with full access to local MCPs (`gsc`, `analytics-mcp`, `ahrefs`, `first-movers-clickup`, `first-movers-wordpress`, `claude_ai_searchable`, `airtable`, `elementor-mcp`, `n8n`) and the direct-REST wrappers in `tools/`. One lightweight `/schedule` routine acts as a heartbeat safety-net: if the local machine is asleep, off, or Claude Code is closed, the heartbeat still pings the ClickUp pipeline status task `86ah3ywyh` so the operator notices. State files in `data/runs/_daily/<DATE>.json` enforce idempotency.

**Runtime caveat (load-bearing):** `/loop` is NOT a headless daemon. It uses `ScheduleWakeup` to fire within a live Claude Code session. If the operator closes Claude Code, the /loop registration dies with it. For the local-first phase this is acceptable for testing — when Claude Code is open, the loops fire; when it's closed, the heartbeat detects the gap and posts to ClickUp. Production 24/7 operation will be addressed in the future VM plan.

**Tech Stack:** Python 3.11+, Claude Code on Windows (operator workstation), `/loop` + `/schedule` skills, MCP servers (gsc, analytics-mcp, ahrefs, first-movers-clickup, first-movers-wordpress, claude_ai_searchable, airtable, elementor-mcp, n8n), pytest for testable code, existing FM-Content tooling.

## Out of scope (deferred to future plan)

- **VM provisioning + always-on hosting.** Cloud VM (Hetzner / Lightsail / etc.), Ubuntu install, Claude Code on Linux, systemd / cron / tmux for persistent runtime. Captured as a follow-up effort once the local-first /loop architecture is proven.
- **Choice of runtime mechanism on VM** (`/loop` in persistent claude session vs `cron + claude -p` headless). Decided during VM plan based on lessons from local-first.

---

## File Structure

**New skill files (each is its own SKILL.md in its own directory):**

| Path | Responsibility |
|---|---|
| `.claude/skills/fm-ahrefs/SKILL.md` | Ahrefs usage across discovery, SERP, keyword research |
| `.claude/skills/fm-gsc/SKILL.md` | Google Search Console striking-distance + per-page query |
| `.claude/skills/fm-ga4/SKILL.md` | GA4 traffic-decay analysis via `tools/ga4.py` direct SDK |
| `.claude/skills/fm-searchable/SKILL.md` | AEO visibility queries via Searchable |
| `.claude/skills/fm-cannibalization/SKILL.md` | Topic overlap gate semantics + defense-in-depth |
| `.claude/skills/fm-prose-generation/SKILL.md` | SERP-to-prose generation method (rubric is the WHAT, this is the HOW) |
| `.claude/skills/fm-wordpress-push/SKILL.md` | WP create_post + Rank Math meta + WAF fallback |
| `.claude/skills/fm-clickup-ops/SKILL.md` | ClickUp task patterns + approval semantics |

**New workflow files:**

| Path | Responsibility |
|---|---|
| `workflows/content-daily-idea-loop.md` | `/loop` variant using all 4 discovery sources |
| `workflows/content-poll-and-draft-loop.md` | `/loop` variant of polling drafter |
| `workflows/heartbeat-canary.md` | `/schedule` safety-net SOP — even more important locally since the workstation may be asleep |
| ~~`workflows/loop-host-setup.md`~~ | DEFERRED to future VM plan (out of scope) |

**Modified files:**

| Path | Change |
|---|---|
| `tools/discover/gsc.py` | Verify response-shape adapter matches actual `mcp__gsc__*` payload + add test |
| `tools/discover/ga4_gap.py` | Verify wiring to `tools/ga4.py` direct SDK + add test |
| `tools/discover/searchable_aeo.py` | Verify Searchable MCP response handling + add test |
| `CLAUDE.md` | Update flow table for hybrid mode |
| `workflows/schedule-registration.md` | Note hybrid mode and link to new workflow files |
| `.claude/skills/firstmovers-blog-rubric/SKILL.md` | Add a "See also" section pointing to the new sibling skills (no content removal — rubric stays canonical) |

**No-touch (run identically in `/loop` or `/schedule` — environment-agnostic):**
- `tools/draft.py`, `tools/slate.py`, `tools/rubric.py`, `tools/cannibalization.py`, `tools/daily.py`, `tools/inventory.py`, `tools/push_wp.py`, `tools/rank_math.py`, `tools/identities.py`

---

## Phase 0 — DEFERRED to future VM plan

The four tasks originally in this phase (VM provisioning, operator setup, secret wiring, MCP smoke-test) are out of scope. They will move to a follow-up plan once the local-first /loop architecture is proven over a 1-2 week observation window on the operator's Windows workstation.

The text below is preserved as a reference draft for the future VM plan.

<details>
<summary>Original Phase 0 content — deferred</summary>

### Task 1: Create the loop-host-setup workflow

**Files:**
- Create: `workflows/loop-host-setup.md`

- [ ] **Step 1: Write the workflow doc**

```markdown
# Loop host VM setup

> **Goal.** Provision an always-on Ubuntu 24.04 VM, install Claude Code, clone FM-Content, wire MCPs and secrets, and verify the local MCP set is reachable from the VM. This is the host that runs the `/loop`s.

## 1. Pick the provider and size

| Provider | Plan | Why |
|---|---|---|
| Hetzner Cloud | CX22 (2 vCPU, 4 GB RAM, €4.51/mo) | Cheapest reasonable. Frankfurt or Helsinki. |
| AWS Lightsail | $7 plan (2 vCPU, 2 GB) | If team is already on AWS. |
| DigitalOcean | Basic $6 (1 vCPU, 1 GB) — TIGHT, skip | RAM too small for Claude Code + Node MCP servers |

Recommend Hetzner CX22 unless team standardization demands otherwise.

## 2. OS + base setup

- Ubuntu 24.04 LTS
- Non-root user `fm` with sudo
- Add SSH pubkey for operator (Aditya)
- `ufw allow 22`, deny all else inbound
- `unattended-upgrades` enabled for security patches only (NOT kernel — reboots break /loop)
- Set timezone to UTC (use Phoenix only inside Python via ZoneInfo)

## 3. Install dependencies

    sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git curl build-essential
    # Node for MCP servers
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt install -y nodejs
    # Claude Code
    npm install -g @anthropic-ai/claude-code

## 4. Clone repo + install Python deps

    cd ~
    git clone <repo-url> FM-Content
    cd FM-Content
    python3.11 -m venv .venv
    source .venv/bin/activate
    pip install -e .

## 5. Copy secrets

`.env` must contain (at minimum):

    AHREFS_API_TOKEN=...
    CLICKUP_API_TOKEN=...
    PEXELS_API_KEY=...           # not used in v1 but keep for v2
    WP_USERNAME=...
    WP_APP_PASSWORD=...
    GA4_PROPERTY_ID=...
    # GSC OAuth tokens are stored where mcp__gsc__ expects them

Copy via `scp` from operator workstation; never paste secrets in git or chat.

## 6. Authenticate Claude Code

    claude login
    # follow the device-code flow; uses the operator's Anthropic account

## 7. Configure MCPs

Create `~/.claude/config.json` (or project-local `.mcp.json`) with the same MCP server entries as the operator's workstation. Critical local-only MCPs:

- `gsc` — needs Google OAuth tokens for the GSC property
- `analytics-mcp` — needs GA4 service-account JSON; KNOWN to hang, prefer `tools.ga4` direct SDK
- `ahrefs` — needs `AHREFS_API_TOKEN` env
- `first-movers-wordpress` — points at `https://firstmovers.ai/wp-json/royal-mcp/v1/mcp`
- `claude_ai_searchable` — claude.ai connector, OAuth in-app
- `airtable` — needs `AIRTABLE_API_KEY`
- `elementor-mcp` / `firstmovers-elementor` — WP elementor REST endpoints

## 8. Smoke-test MCPs

In a `claude` session on the VM:

    Skill(skill="fm-ahrefs")
    # then try the canonical Ahrefs MCP call:
    mcp__ahrefs__site-explorer-organic-keywords(target="mckinsey.com", mode="subdomains", date="<today>", limit=10, ...)

Repeat for each MCP. Document any that fail.

## 9. systemd unit for `/loop` host

Create `/etc/systemd/system/fm-content-loop.service`:

    [Unit]
    Description=FM-Content /loop Claude Code session
    After=network.target

    [Service]
    Type=simple
    User=fm
    WorkingDirectory=/home/fm/FM-Content
    ExecStart=/usr/bin/claude --resume <session-id-or-cli-flag>
    Restart=always
    RestartSec=30

    [Install]
    WantedBy=multi-user.target

Enable: `sudo systemctl enable --now fm-content-loop`.

## 10. Monitoring

- `journalctl -u fm-content-loop -f` for live logs
- Optional: forward to Better Stack / Datadog / Logtail
- Heartbeat /schedule (see workflows/heartbeat-canary.md) fires every 12h independent of the VM
```

- [ ] **Step 2: Commit**

```bash
git add workflows/loop-host-setup.md
git commit -m "docs(workflows): VM provisioning + Claude Code install checklist for /loop host"
```

### Task 2: Operator provisions the VM (manual)

**Files:** none (operator action)

- [ ] **Step 1: Provision the VM following workflows/loop-host-setup.md sections 1-3**

Manual operator action. Expected outcome: Ubuntu 24.04 LTS VM with non-root sudo user `fm`, Python 3.11+, Node 22+, Claude Code installed, repo cloned, `.venv` set up.

- [ ] **Step 2: Verify base install**

Run on VM:

```bash
claude --version
python3.11 --version
node --version
cd ~/FM-Content && source .venv/bin/activate && python -c "import tools; print(tools)"
```

Expected: all four commands succeed without error.

### Task 3: Wire secrets and MCPs on VM

**Files:**
- Create on VM: `~/FM-Content/.env`
- Create on VM: `~/.claude/config.json` (or `~/FM-Content/.mcp.json` depending on Claude Code MCP config preference)

- [ ] **Step 1: Copy .env from operator workstation**

```bash
scp .env fm@<vm-host>:~/FM-Content/.env
ssh fm@<vm-host> chmod 600 ~/FM-Content/.env
```

- [ ] **Step 2: Configure MCP servers**

Copy MCP server definitions (paths to gsc OAuth, GA4 service account, etc.). Validate JSON.

- [ ] **Step 3: claude login on VM**

```bash
ssh fm@<vm-host>
claude login
# device-code flow
```

Expected: `claude` session opens cleanly, login persisted to `~/.config/claude/`.

### Task 4: Smoke-test all 9 MCPs from VM

**Files:** none (runtime verification only)

- [ ] **Step 1: Start a claude session on the VM and run each MCP**

```bash
ssh fm@<vm-host>
cd ~/FM-Content
claude
```

Inside the session, invoke each MCP's lightest call and capture the response. Verify all return real data, not connection errors:

| MCP | Smoke call |
|---|---|
| `mcp__ahrefs__site-explorer-domain-rating` | `target="firstmovers.ai"` |
| `mcp__gsc__list_properties` | (no args) |
| `mcp__analytics-mcp__get_account_summaries` | (no args — and confirm whether it hangs; if so, document and rely on `tools/ga4.py`) |
| `mcp__first-movers-wordpress__wp_get_site_info` | (no args) |
| `mcp__first-movers-clickup__clickup_get_workspace_hierarchy` | (no args) |
| `mcp__claude_ai_searchable__list_projects` | (no args) |
| `mcp__airtable__list_bases` | (no args) |
| `mcp__firstmovers-elementor__get_page` | use a known page id |
| `mcp__n8n__n8n_health_check` | (no args) |

- [ ] **Step 2: Document results in workflows/loop-host-setup.md**

Append a "VM smoke-test results <ISO date>" table to the workflow noting which MCPs returned real data and which required workarounds.

- [ ] **Step 3: Commit any workflow notes**

```bash
git add workflows/loop-host-setup.md
git commit -m "docs(workflows): record VM MCP smoke-test results"
```

</details>

---

## Phase 1 — Discovery + SEO Skill Files (4 skills)

### Task 5: Write fm-ahrefs/SKILL.md

**Files:**
- Create: `.claude/skills/fm-ahrefs/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-ahrefs
description: Use when calling any Ahrefs endpoint in the FM-Content pipeline — competitor gap discovery, SERP intent, keyword research, or per-post backlink/traffic snapshots. Covers MCP-vs-direct-REST routing, monetary unit convention (USD cents), competitor rotation, common pitfalls, and failure modes.
---

# Ahrefs in FM-Content

Ahrefs is the primary keyword-and-competitor signal for the pipeline. This skill captures which endpoint to call when, the conventions you must respect, and the failure modes you'll hit.

## When to use which endpoint

| Need | Endpoint | Wrapper |
|---|---|---|
| Find topics a competitor ranks for that we don't | `mcp__ahrefs__site-explorer-organic-keywords` | `tools/discover/ahrefs_gap.py::discover` |
| What does the SERP look like for this keyword | `mcp__ahrefs__serp-overview` | called inline in `tools/draft.py` |
| Volume / KD / parent topic for a keyword | `mcp__ahrefs__keywords-explorer-overview` | called in `tools/inventory_refresh.py` |
| Variant keywords for a topic | `mcp__ahrefs__keywords-explorer-matching-terms` | used in inventory join |
| Our backlink profile | `mcp__ahrefs__site-explorer-backlinks-stats` | inventory only |
| All organic keywords for one of our posts | `mcp__ahrefs__site-explorer-organic-keywords` (target=firstmovers.ai URL) | inventory join |

## MCP vs direct REST

| Runtime | Use |
|---|---|
| `/loop` on VM (default going forward) | `mcp__ahrefs__*` MCP tools OR `tools.ahrefs.*` direct REST — both work. Prefer MCP for parity with anything that might still run in `/schedule`. |
| `/schedule` cloud routine | `mcp__ahrefs__*` MCP tools ONLY (the claude.ai Ahrefs connector, UUID `09f92d25-0521-43d1-8b8e-d3124f9073e4`). Direct REST is blocked by the sandbox proxy ("Host not in allowlist"). |
| Local pytest / ad-hoc scripts | `tools.ahrefs.*` direct REST with `AHREFS_API_TOKEN` env. |

## Monetary unit convention (CRITICAL)

All monetary fields across Ahrefs v3 are returned in **USD cents**, not dollars: `value`, `org_cost`, `paid_cost`, `traffic_value`. Divide by 100 to display in USD. This trips up every new contributor — `tools/discover/ahrefs_gap.py` already does the division, so prefer routing through the discover module rather than calling the endpoint raw.

## Competitor rotation (daily-idea routine)

To keep the daily Ahrefs cost bounded, the daily routine rotates one competitor per weekday:

| Day (Phoenix) | Target | Why |
|---|---|---|
| Monday | mckinsey.com | strategy giant |
| Tuesday | bcg.com | strategy giant |
| Wednesday | bain.com | strategy giant |
| Thursday | hubspot.com | inbound playbook owner |
| Friday | accenture.com | enterprise AI |
| Saturday | deloitte.com | tax+advisory |
| Sunday | mckinsey.com | freshest signal for week-ahead planning |

In a /loop daily run we layer **GSC striking-distance** and **GA4 decay** on top, so Ahrefs alone is no longer the sole signal. But it's still the seed for competitor-gap candidates.

## Common pitfalls

1. **`mode` matters.** `mode="subdomains"` for company-wide pulls, `mode="domain"` for a single domain. Pulling McKinsey with `mode="domain"` will miss `www.mckinsey.com` vs root.
2. **`date` is required for v3 endpoints.** Pass today's date in `YYYY-MM-DD`.
3. **`limit=100` is the sweet spot.** 1000+ explodes payload size and the cannibalization gate runtime.
4. **`order_by="sum_traffic:desc"`** — sort by traffic, NOT by keyword volume. Traffic accounts for competitor's actual rank.
5. **`select=` is mandatory for column selection.** Without it you get the default columns which may not include `keyword_difficulty`.

## Failure modes

| Symptom | Diagnosis | Fix |
|---|---|---|
| `403 "Host not in allowlist"` | Direct REST call from inside `/schedule` routine | Switch to `mcp__ahrefs__*` |
| `429 Too Many Requests` | Quota exhausted | Wait until UTC midnight reset; rotate competitor to one with lower depth |
| Empty `keywords` array | Wrong `mode` or `target` typo | Validate target with `site-explorer-domain-rating` first |
| Stale data (older than ~14 days) | Ahrefs index lag for that domain | Acceptable — Ahrefs doesn't crawl every domain daily |

## Render-with metadata

Some Ahrefs endpoints return a `render_with` field in metadata. You MUST call the specified render tool (`mcp__ahrefs__render-data-table`, `mcp__ahrefs__render-scorecard`, `mcp__ahrefs__render-time-series-chart`) with the returned data. Don't summarize raw data without rendering it first — this is per Ahrefs MCP server instructions.
```

- [ ] **Step 2: Verify skill loads**

In a Claude Code session, invoke:

```
Skill(skill="fm-ahrefs")
```

Expected: skill content rendered to context with no YAML parse error. If error, fix frontmatter (check `name` matches directory name, `description` is one line).

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-ahrefs/SKILL.md
git commit -m "feat(skills): fm-ahrefs — Ahrefs usage skill for /loop pipeline"
```

### Task 6: Write fm-gsc/SKILL.md

**Files:**
- Create: `.claude/skills/fm-gsc/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-gsc
description: Use when calling Google Search Console MCP for striking-distance discovery, per-page query diagnosis, or inventory join. Covers position-band semantics, OAuth refresh, the /loop-only constraint (no claude.ai connector exists for GSC), and how to feed signals into tools/discover/gsc.py.
---

# Google Search Console in FM-Content

GSC is the highest-conviction discovery signal we have because it's first-party — these are queries the FirstMovers.ai site is **already showing up for**, not hypothetical opportunities. The job is to find the queries where one good push moves us from page 2 to page 1.

## Critical constraint — /loop only

As of 2026-05-09 there is no claude.ai built-in MCP connector for GSC. The `mcp__gsc__*` tools only exist in the local MCP environment (your workstation or the VM). Therefore:

- `/schedule` routines CANNOT use GSC. Don't try.
- `/loop`s on the VM CAN use it.
- This is the #1 reason FM-Content is migrating off `/schedule` for discovery.

## When to use which endpoint

| Need | Endpoint |
|---|---|
| Striking-distance keywords (positions 4-15 with real impressions) | `mcp__gsc__get_search_analytics` with dimensions `["query"]` |
| Why is a specific URL underperforming | `mcp__gsc__get_search_by_page_query` |
| All keywords for a given page | `mcp__gsc__get_advanced_search_analytics` with page filter |
| Compare last 28d to prior 28d | `mcp__gsc__compare_search_periods` |
| Site-level health overview | `mcp__gsc__get_performance_overview` |

## Striking-distance query

This is the workhorse for discovery:

    mcp__gsc__get_search_analytics(
      site_url="https://firstmovers.ai/",
      start_date="<today minus 28>",
      end_date="<today>",
      dimensions=["query", "page"],
      row_limit=500,
      data_state="final",
    )

Then in Python:

    from tools.discover.gsc import discover
    cands = discover(gsc_response, inventory)

The filter is "position between 4 and 15, impressions >= 50, CTR < expected for position". `tools/discover/gsc.py` does this; don't reimplement.

## Position bands

| Position | Action |
|---|---|
| 1-3 | Already winning. Skip unless CTR is terrible (title rewrite candidate). |
| 4-10 | **Striking distance.** One good push moves us to page 1. Highest-leverage. |
| 11-15 | **Striking distance with effort.** Worth it if impressions >= 200. |
| 16-30 | Page 2/3. Usually means content gap or weak topical authority — bigger project than a single post. |
| 30+ | Ignore for discovery; might come up in cannibalization gate as "noise rank". |

## OAuth refresh

GSC uses Google OAuth. On the VM, tokens live at the path the `mcp__gsc__*` server expects (typically `~/.config/gsc-mcp/token.json` or similar — check the server's docs).

If you see `401 invalid_grant`, the refresh token has expired (Google revokes after 6 months of inactivity OR if the user revokes app access). Fix:

1. Run `mcp__gsc__reauthenticate` in a claude session on the VM
2. Follow the device-code flow
3. New token persisted to disk; subsequent calls succeed

## Failure modes

| Symptom | Diagnosis |
|---|---|
| Empty rows even though site has traffic | `data_state="final"` excludes last 2-3 days. Try `data_state="all"` |
| `403 Forbidden` | Service account / user lacks "Restricted" permission on the GSC property |
| `429` | Per-property quota — back off and retry in 60s |
| `mcp__gsc__list_properties` returns empty | Wrong OAuth scope or wrong Google account |
```

- [ ] **Step 2: Verify skill loads**

```
Skill(skill="fm-gsc")
```

Expected: rendered cleanly.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-gsc/SKILL.md
git commit -m "feat(skills): fm-gsc — Google Search Console usage skill"
```

### Task 7: Write fm-ga4/SKILL.md

**Files:**
- Create: `.claude/skills/fm-ga4/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-ga4
description: Use when querying Google Analytics 4 to detect traffic decay on published posts (which posts need refresh vs which need replacement). Covers the analytics-mcp-hangs workaround via tools/ga4.py, the decay-detection query, and how to feed into tools/discover/ga4_gap.py.
---

# Google Analytics 4 in FM-Content

GA4 is how we detect **traffic decay** — pages that used to rank, slipped, and need either a refresh or a replacement post. This is the third discovery source (after Ahrefs gap and GSC striking-distance) and the one that surfaces "fix what's broken" candidates rather than "find net-new" ones.

## Critical constraint — use the direct SDK, not the MCP

`mcp__analytics-mcp__*` hangs on most queries (observed 2026-04 and again 2026-05). DO NOT rely on it for production.

Instead, use `tools/ga4.py` which wraps `google-analytics-data` SDK directly. Same auth (GA4 service account JSON), no MCP middleman.

    from tools.ga4 import run_report

    rows = run_report(
        property_id="<GA4_PROPERTY_ID>",
        dimensions=["pagePath"],
        metrics=["sessions", "engagedSessions"],
        date_ranges=[
            {"start_date": "29daysAgo", "end_date": "yesterday"},
            {"start_date": "57daysAgo", "end_date": "30daysAgo"},
        ],
        limit=500,
    )

## Decay detection

A post is "decaying" if:

- Last 28d sessions < 60% of prior 28d sessions, AND
- Prior 28d sessions >= 50 (i.e., it had real traffic to lose), AND
- Page path matches an inventory entry (i.e., it's our content, not someone else's)

`tools/discover/ga4_gap.py` does this filter. Feed it the rows from `tools.ga4.run_report` and the inventory snapshot; it returns candidate proposals tagged as `discovery_source="ga4-decay"`.

## When to use GA4 vs GSC

| Question | Source |
|---|---|
| "What new query should we write about?" | GSC striking-distance |
| "Which existing post is bleeding traffic?" | GA4 decay |
| "Did this post lose its rank or its CTR?" | GSC `get_search_by_page_query` (then compare to GA4 sessions) |
| "Is the site overall up or down quarter-over-quarter?" | GA4 `compare_search_periods`-style |

GSC tells you about impressions and rank. GA4 tells you about sessions. Decay shows up in GA4 first because GSC's rank changes propagate to GA4 sessions with ~7-day lag.

## Auth

Service account JSON at the path `tools/ga4.py` expects (env var `GOOGLE_APPLICATION_CREDENTIALS` or its own config). Service account needs "Viewer" role on the GA4 property.

## Failure modes

| Symptom | Diagnosis |
|---|---|
| `PERMISSION_DENIED` | Service account not added to GA4 property OR wrong property ID |
| All rows have 0 sessions | Date range too narrow OR property has no data (check in GA4 UI) |
| `run_report` hangs > 30s | DON'T retry into the MCP. Use the SDK directly via `tools.ga4`. |
```

- [ ] **Step 2: Verify skill loads**

```
Skill(skill="fm-ga4")
```

Expected: rendered cleanly.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-ga4/SKILL.md
git commit -m "feat(skills): fm-ga4 — GA4 decay detection skill"
```

### Task 8: Write fm-searchable/SKILL.md

**Files:**
- Create: `.claude/skills/fm-searchable/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-searchable
description: Use when querying Searchable.ai for AEO (Answer Engine Optimization) visibility data — which AI search queries FirstMovers.ai shows up for, which topics we're cited on, share-of-voice vs competitors. Covers the visibility endpoints and how to feed into tools/discover/searchable_aeo.py.
---

# Searchable in FM-Content

Searchable.ai tracks brand visibility in **AI search engines** — ChatGPT, Perplexity, Claude, Gemini — which is a different signal from Google SERP. This is the fourth discovery source: "topics we're being cited on that we don't have content for yet."

## When to use which endpoint

| Need | Endpoint |
|---|---|
| Which prompts has FirstMovers been mentioned in | `mcp__claude_ai_searchable__get_visibility_by_prompt` |
| Which topics drive that visibility | `mcp__claude_ai_searchable__get_visibility_by_topic` |
| Overall share-of-voice snapshot | `mcp__claude_ai_searchable__get_visibility_summary` |
| Historical trend (visibility over time) | `mcp__claude_ai_searchable__get_visibility_history` |
| Why is a specific prompt's visibility shifting | `mcp__claude_ai_searchable__get_visibility_details` |

## AEO vs SEO

AEO signal is fundamentally different from SEO:

- **SEO (GSC, Ahrefs):** "people Google'd this query and saw our site." Volume + position.
- **AEO (Searchable):** "an AI assistant answered a question and cited (or didn't cite) our site." Mention + sentiment.

The two often disagree. A page can rank #1 on Google and be invisible in ChatGPT (and vice versa). For FM-Content, AEO discovery surfaces:

- Topics where a competitor is the dominant AI citation and we're nowhere → write the answer better than them.
- Topics where AI assistants quote our content positively → expand on those (they're proof we're already authoritative).

## Feed into discover

    from tools.discover.searchable_aeo import discover
    cands = discover(searchable_response, inventory)

The discover module filters for prompts where:
- We appear in top 10 cited sources (`mention_rank <= 10`), OR
- The prompt's topic matches an inventory category but we have NO post for it yet (pure gap)

## Cadence

Searchable data updates daily but the visibility numbers are noisy at the day level. Use 7-day windows for trend, 28-day for stability.

## Failure modes

| Symptom | Diagnosis |
|---|---|
| `401 Unauthorized` | Searchable connector re-auth needed. Run `mcp__claude_ai_searchable__authenticate` |
| Empty `visibility` array | Project not configured in Searchable for the FirstMovers domain |
| Different domain in response | Wrong project_id; check `mcp__claude_ai_searchable__list_projects` |
```

- [ ] **Step 2: Verify skill loads**

```
Skill(skill="fm-searchable")
```

Expected: rendered cleanly.

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-searchable/SKILL.md
git commit -m "feat(skills): fm-searchable — AEO visibility skill"
```

---

## Phase 2 — Process Skill Files (4 skills)

### Task 9: Write fm-cannibalization/SKILL.md

**Files:**
- Create: `.claude/skills/fm-cannibalization/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-cannibalization
description: Use before proposing any new blog topic or right before assembling a draft. Captures the cannibalization gate semantics (the v5 bug that motivated rebuilding the pipeline), severity ladder, evidence fields, defense-in-depth re-check at draft time, and StaleInventoryError handling.
---

# Cannibalization gate

The single most load-bearing rule in FM-Content: **never propose a topic that overlaps a topic FirstMovers.ai has already published.** That was the v5 bug; this gate is the structural defense.

## Why the gate exists

Pre-rebuild (v5), the pipeline shipped 14 posts in three months that competed with existing posts on the same focus keyword. Google de-ranked both. Traffic dropped 22% before anyone caught it.

The gate (`tools/cannibalization.py::evaluate`) compares a `ProposedTopic` against every entry in the inventory snapshot on five signals:

1. **Focus keyword exact match** — fatal
2. **Focus keyword high semantic overlap** (cosine ≥0.85 via embedding) — severity `high`
3. **Top-3 organic keyword overlap >= 2 keywords** — severity `high`
4. **Title fuzzy match (Levenshtein ratio >= 0.75)** — severity `medium`
5. **Same Tier-1 internal-link target (would compete for the same `/consulting/` or `/labs/` page)** — severity `low`

## Severity ladder + action

| Severity | Action | When |
|---|---|---|
| `critical` | **Hard block.** Never propose to Nikki. | Exact focus keyword match |
| `high` | **Hard block.** Never propose to Nikki. | Semantic overlap or 2+ shared top organic keywords |
| `medium` | **Advisory.** Surface to Nikki with the conflict noted; she decides. | Title fuzzy match |
| `low` | **Info only.** Note in the proposal but don't gate. | Internal-link competition |

In `tools/slate.py` and `tools/daily.py`, anything `critical` or `high` is filtered out before reaching the top-N candidate selection. In `tools/draft.py::prepare_brief`, the gate runs AGAIN as defense-in-depth — if inventory changed between slate emission (Sunday) and draft generation (Wednesday or any approval poll), a topic that was clear can become a `critical` overlap.

## Evidence fields

Every gate evaluation returns an `evidence` dict:

```json
{
    "matched_post_url": "https://firstmovers.ai/blog/ai-consulting-roi/",
    "matched_focus_keyword": "ai consulting roi",
    "match_type": "focus_keyword_exact",
    "embedding_similarity": 1.0,
    "shared_top_keywords": ["ai consulting roi", "ai consulting price"]
}
```

These fields are persisted as `discovery_evidence` on the daily/slate proposal. They show up on the ClickUp task for Nikki's audit trail.

## StaleInventoryError

`inv.assert_fresh()` raises `StaleInventoryError` if the inventory snapshot is more than 7 days old. The gate is only as good as the inventory it compares against — running it against a stale snapshot is worse than not running it at all because it gives false confidence.

When you see `StaleInventoryError`:

1. Do NOT bypass it.
2. Run `python -m tools.inventory_refresh` to refresh.
3. Re-run the discovery + gate.

## Idempotency

The gate is deterministic given the same `(ProposedTopic, Inventory)` input. Re-running it produces the same severity. This means the draft-time re-check is cheap insurance, not a correctness fix.

## Failure modes

| Symptom | Cause |
|---|---|
| Gate returns `critical` on a topic that's clearly novel | Inventory has a stub post with the same focus keyword. Audit `data/inventory/firstmovers-ai.json` for that entry; may be a v4 ghost. |
| Gate returns `none` on an obvious dup | Inventory entry has `focus_keyword == None`. Refresh inventory; the gate refuses to run on degraded entries via `assert_complete()`. |
| `StaleInventoryError` even after refresh | Check `data/inventory/firstmovers-ai.json` mtime. If clock skewed (VM time off), fix VM time. |
```

- [ ] **Step 2: Verify skill loads**

```
Skill(skill="fm-cannibalization")
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-cannibalization/SKILL.md
git commit -m "feat(skills): fm-cannibalization — gate semantics + severity ladder"
```

### Task 10: Write fm-prose-generation/SKILL.md

**Files:**
- Create: `.claude/skills/fm-prose-generation/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-prose-generation
description: Use when generating the body of a FirstMovers.ai blog draft. This is the method skill (HOW to write); pair with firstmovers-blog-rubric (WHAT to hit). Covers the 5-step prose workflow, section pacing, citation density, internal/external link weaving, and the retry-on-RubricViolation loop.
---

# Prose generation method

This skill is paired with `firstmovers-blog-rubric`:
- **`firstmovers-blog-rubric`** = the target (Rank Math 19-check rubric, profile stats, allowlists)
- **`fm-prose-generation`** = the method (how to actually write the body that hits the target)

## The 5-step workflow

### 1. Load the rubric

    Skill(skill="firstmovers-blog-rubric")

You'll need power words, internal/external link allowlists, audience routing (DFY → /consulting/, DIY → /labs/), and the don'ts list (no em dashes, no "free audit", no trailing period in titles).

### 2. Fetch SERP context

    serp = mcp__ahrefs__serp-overview(
        keyword=focus_keyword,
        country="us",
        top_positions=10,
        select="title,url,position,domain_rating,backlinks,traffic,top_keyword",
    )

Read the top-10 titles and meta descriptions. This is what you must out-write. Identify:
- What angles ARE everyone taking (skip those)
- What angle is missing (lead with that)
- What domain authority you're up against (DR60+ means you need stronger citations than them)

### 3. Draft

Outline first, then prose. Target:
- **≥ 2,500 words, target 3,500** (firstmovers-blog-rubric §1)
- **≥ 6 H2 sections, target 7** (median of published posts is 7)
- **At least 1 H2 contains the focus keyword** (Rank Math additional check)
- **Lede mentions focus keyword in first paragraph**
- **Paragraphs < 120 words each** (Rank Math grades this)
- **≥ 3 external dofollow citations** from `external_links.curated_for(category_id)` (target 6+)
- **One audience-routed CTA** at the end (DFY → "Schedule a Free Strategy Call" → `/consulting/`; DIY → "Explore AI Labs" → `/labs/`)
- **3 internal "read next" links** at the bottom, audience-matched

### Section pacing template

| Section | Purpose | Words |
|---|---|---|
| Lede (no H2) | Mention focus keyword, set stakes, promise the answer | 60-120 |
| H2 #1 — Frame the problem | Why this matters now (cite a recent stat) | 350-500 |
| H2 #2 — Definitions / context | The thing the AI search assistants will quote | 350-500 |
| H2 #3 — Core argument (focus kw in heading) | Your differentiated take | 500-700 |
| H2 #4 — Evidence / case studies | 2-3 concrete examples with stats | 400-600 |
| H2 #5 — How to do it / framework | Numbered or bulleted, operator-grade | 400-600 |
| H2 #6 — Common mistakes / objections | What competitors miss | 300-500 |
| H2 #7 — What to do next | Actionable summary, NOT a CTA | 200-300 |
| FAQ | 3-7 question/answer pairs, AEO-friendly | varies |
| CTA block | Audience-routed | 60-100 |
| Read next aside | 3 internal links | 30 |

### 4. Citation density

Target: **one external citation per 300-400 words.** A 3,500-word post should have ~10 citations. The published median is 11. Spread them across H2s — not all in one section.

Curated citations only (HBR, McKinsey, BCG, Bain, Deloitte, Gartner, Stanford HAI, MIT Sloan, MIT Tech Review, WEF, OECD, Anthropic, OpenAI, Google DeepMind, Salesforce, HubSpot, CMI, The Verge).

**Never cite:** PwC, Accenture, Capgemini, IBM, doneforyou.com, automationagency.com, ugenticai.com.

### 5. Validate + retry

    try:
        assembled = assemble(brief, body_html=body, faq_items=faqs, seo_title=seo, meta_description=meta)
    except RubricViolation as e:
        # e.message names the exact rule violated
        # regenerate the prose addressing the named rule; retry up to 2 times
        ...

The retry loop is capped at 2 because if the model can't get it right in 3 tries, something structural is wrong (usually: focus keyword is too narrow, SERP is dominated by domain authority we can't match, OR external_links.curated_for returned an empty list for that category).

## Internal link weaving

The `internal_links.select(audience, exclude_url, max_total=5)` helper picks 5 audience-relevant internal links. You weave them into the body naturally — not in a bibliography at the end.

Inline. Anchored on the relevant phrase. Never `utm_source=internal` (nukes GA4 attribution per firstmovers-blog-rubric §11).

## What "good prose" looks like (style guide)

- **Sentence length variance.** Mix 6-word sentences with 25-word sentences. Pure long sentences scan as AI; pure short sentences scan as bullet-point summary.
- **Concrete over abstract.** "McKinsey's 2024 generative-AI survey found 65% of orgs report regular use, up from 33% the year prior" beats "AI adoption is growing."
- **No em dashes.** Hyphens only. (Josh April 2026 directive.)
- **No "free audit".** Anywhere. Consulting is $25-60K.
- **No marketing voice.** First Movers is a B2B consulting firm; the prose should read like a senior consultant writing, not a content marketer.
- **Operator-grade specifics.** When listing steps or frameworks, the steps must be doable. Avoid "leverage AI" / "drive value" — name the tool, name the metric.

## Don't

- Don't generate `<h1>` in the body (WP renders the title as page H1).
- Don't generate BlogPosting or BreadcrumbList JSON-LD (Rank Math emits those).
- Don't emit `[AFFILIATE_LINK:TOOLNAME]` tokens — no resolver in pipeline.
- Don't include images in the body (v1 ships text-only per firstmovers-blog-rubric §6).
- Don't trail the post title with a period.
```

- [ ] **Step 2: Verify skill loads**

```
Skill(skill="fm-prose-generation")
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-prose-generation/SKILL.md
git commit -m "feat(skills): fm-prose-generation — method skill for blog body drafting"
```

### Task 11: Write fm-wordpress-push/SKILL.md

**Files:**
- Create: `.claude/skills/fm-wordpress-push/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-wordpress-push
description: Use when pushing a validated draft to WordPress as status=draft, setting Rank Math meta, or handling WAF blocks via the Path B fallback. Covers wp_create_post payload assembly, Rank Math meta keys, post_author=3, valid category IDs, and the GH Actions WAF-bypass workflow.
---

# WordPress push

The terminal step of the pipeline: turn a validated `AssembledDraft` into a WordPress post with `status="draft"` so Nikki can review and publish.

## Hard rules (enforced by `tools/push_wp.py`)

| Rule | Why | Where enforced |
|---|---|---|
| `status="draft"` always | Only Nikki publishes | `build_create_payload` |
| `post_author=3` (Josh McCoy) | Single source of truth, `tools/identities.py::WP_AUTHOR_JOSH` | `build_create_payload` |
| Category in `VALID_WP_CATEGORY_IDS` ({27, 28, 29, 30, 13, 14, 10}) | Hand-curated; never invent new categories without Nikki approval | `_validate_category_id` |
| Endpoint host must be `firstmovers.ai` | No accidental cross-site pushes | `_assert_host` |

## The push call

    from tools.push_wp import build_create_payload
    from tools.rank_math import build_meta

    payload = build_create_payload(
        title=assembled.title,
        content=assembled.body_html,
        slug=assembled.slug,
        excerpt=assembled.excerpt,
        category_id=assembled.category_id,
    )

    wp = wp_create_post(
        title=payload.title,
        content=payload.content,
        excerpt=payload.excerpt,
        slug=payload.slug,
        status="draft",
        categories=payload.categories,
        post_author=3,
    )
    post_id = int(wp["id"])

## Rank Math meta

After post creation, set three Rank Math meta keys:

    rm = build_meta(
        focus_keyword=assembled.focus_keyword,
        seo_title=assembled.seo_title,
        meta_description=assembled.meta_description,
        slug=assembled.slug,
    )

    for key, value in [
        ("rank_math_focus_keyword", rm.focus_keyword),
        ("rank_math_title", rm.seo_title),
        ("rank_math_description", rm.meta_description),
    ]:
        wp_update_post_meta(post_id=post_id, key=key, value=value)

`rank_math_title` and `rank_math_description` override the WP default title/excerpt for SERP rendering. `rank_math_focus_keyword` powers the 19-check rubric grading inside the WP admin.

## Featured image

In v1: left blank. Nikki adds it post-publish. Do NOT call `wp_set_featured_image` from the pipeline.

## WAF fallback (Path B)

The Cloudways WAF intermittently blocks REST `POST` to `/wp-json/wp/v2/posts`. Symptom: 403 from `wp_create_post` with body like `"Your request was blocked. Please contact support."`

Detection + queue:

    from tools.push_wp import queue_for_path_b, is_waf_block

    try:
        wp = wp_create_post(...)
    except Exception as e:
        if is_waf_block(e):
            queue_for_path_b(assembled, target_dir="data/runs/_pending-push/")
            # leave state at 'approved', not 'drafted'
            # then trigger Path B:
            subprocess.run(["gh", "workflow", "run", "wp-push-fallback.yml", "--ref", "main"])
            return
        raise

Path B runs from GitHub Actions (different egress IP, bypasses the WAF rule).

## Audience routing — CTA destination must match

This is enforced in `tools.draft.assemble`, not in `push_wp`, but it's worth restating: a `done-for-you` post must NOT have a `/labs/` CTA, and vice versa. Mixing them is a hard-fail rubric violation.

## Post-push: comment on the ClickUp task

After successful push, comment on the daily-state's ClickUp task:

    clickup_create_task_comment(
        task_id=state.clickup_task_id,
        comment_text=(
            f"Drafted to WordPress.\n\n"
            f"- Edit: https://firstmovers.ai/wp-admin/post.php?post={post_id}&action=edit\n"
            f"- Preview: https://firstmovers.ai/?p={post_id}&preview=true\n"
            f"- Word count: {wc:,}\n"
            f"- Author: Josh McCoy (post_author=3)\n\n"
            f"Nikki: review, set slug if needed ({assembled.slug}), add featured image, "
            f"get Josh CTA approval, publish, NitroPack purge."
        ),
    )

## Failure modes

| Symptom | Diagnosis |
|---|---|
| `403 "Your request was blocked"` | WAF. Queue to Path B. |
| `400 "invalid_param" for categories` | Category not in `VALID_WP_CATEGORY_IDS`. Check `tools/identities.py`. |
| `401 Unauthorized` | App password expired or revoked in WP admin. Regenerate. |
| Post created but Rank Math meta missing | `wp_update_post_meta` failed silently; retry, then verify in WP admin |
| Post `post_author` is 1 (admin) not 3 | `post_author=3` not passed to `wp_create_post`. Always pass explicitly. |
```

- [ ] **Step 2: Verify skill loads**

```
Skill(skill="fm-wordpress-push")
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-wordpress-push/SKILL.md
git commit -m "feat(skills): fm-wordpress-push — WP push + Rank Math + WAF fallback"
```

### Task 12: Write fm-clickup-ops/SKILL.md

**Files:**
- Create: `.claude/skills/fm-clickup-ops/SKILL.md`

- [ ] **Step 1: Write the skill file**

```markdown
---
name: fm-clickup-ops
description: Use when creating ClickUp tasks for Nikki, polling task status for approvals, or commenting on the pipeline status task. Covers task-creation patterns, approval semantics, workspace/list/user IDs from tools/identities.py, and when to comment vs not.
---

# ClickUp operations

ClickUp is the human-loop surface. Three operations matter: **create** (daily idea emit), **read** (approval polling), **comment** (status + traceability).

## Canonical IDs

From `tools/identities.py`:

| Name | ID | Purpose |
|---|---|---|
| Workspace | `9013404166` | Top-level team |
| List: Content Projects | `901326229295` | Where daily-idea tasks land |
| Task: Pipeline Status | `86ah3ywyh` | Heartbeat / status comment sink |
| User: Nikki | `26221739` | Assignee for daily-idea tasks |
| User: Josh | `120239313` | CTA approver (informational, not assigned) |

Always import from `tools.identities`, NEVER hardcode in workflows or skills.

## Create a daily task

    resp = clickup_create_task(
        list_id="901326229295",
        name=f"[{today}] {proposal['working_title']}",
        markdown_description=<rich block with proposal details + evidence>,
        assignees=[26221739],   # Nikki
        due_date=today,         # YYYY-MM-DD; ClickUp accepts ISO date string
        tags=["fm-content-daily"],
    )
    task_id = resp.get("task_id") or resp.get("id")

The `markdown_description` block should contain:
- Focus keyword
- Working title
- Audience (DFY or DIY)
- Discovery source + evidence
- Estimated traffic / KD / volume
- Cannibalization gate result

This is what Nikki reads to decide approve/decline.

## Poll for approval

    resp = clickup_get_task(task_id=state.clickup_task_id, detail_level="summary")
    from tools.daily import is_task_approved
    approved, status_name = is_task_approved(resp)

`is_task_approved` returns `True` if:
- Status `type` field in `{"done", "closed"}`, OR
- Status `name` in `{"published", "complete", "closed", "done", "ready"}`

(case-insensitive on the name check)

This handles ClickUp workspace variability where teams customize status names.

## Comment patterns

### When to comment

| Event | Comment on | What |
|---|---|---|
| Routine start (canary) | `86ah3ywyh` | `"Routine X started at <iso>"` — only if there's pending work, else suppress |
| Daily idea emitted | new task | Auto-handled by `clickup_create_task` body |
| Approval polled successfully | `state.clickup_task_id` | (no comment — silent mark_approved is fine) |
| Draft pushed to WP | `state.clickup_task_id` | Full comment with edit URL, preview URL, word count, post-publish checklist |
| Cannibalization conflict at draft time | `state.clickup_task_id` | Explain the conflict; do NOT push the draft |
| Rubric violation 3x in a row | `state.clickup_task_id` | Note the violated rule; skip until next polling cycle |
| Run summary | `86ah3ywyh` | Only when state actually advanced — silent no-op runs don't comment |

### Don't comment

- Idempotent skips (already drafted) — silent
- Empty runs (no pending work) — silent (or one daily no-op comment at most)
- Diagnostic / debug info — log to disk, don't pollute ClickUp

## Status task `86ah3ywyh` — the canary

This is the central pipeline-health signal. Comments here are read by operators (Aditya) NOT by Nikki.

Use it for:
- Routine start / end heartbeat
- Run summaries ("Polling drafter run: 1 newly approved, 1 drafted, 2 still awaiting")
- Failure reports (with full traceback)
- Drift alerts (inventory >7 days old, etc.)

## Failure modes

| Symptom | Diagnosis |
|---|---|
| `404` on `clickup_get_task` | Task deleted between emit and poll. Treat as not-approved; continue. |
| Comment lands but assignee field is empty on the task | Wrong assignee ID. Check `tools.identities.NIKKI_CLICKUP_ID`. |
| Status name customized to "Approved" | Add it to `is_task_approved`'s accepted set; commit + push. |
| `401 Unauthorized` (direct REST only) | `CLICKUP_API_TOKEN` expired. Regenerate from ClickUp settings. |
```

- [ ] **Step 2: Verify skill loads**

```
Skill(skill="fm-clickup-ops")
```

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/fm-clickup-ops/SKILL.md
git commit -m "feat(skills): fm-clickup-ops — ClickUp task + approval semantics"
```

### Task 13: Update firstmovers-blog-rubric to point at sibling skills

**Files:**
- Modify: `.claude/skills/firstmovers-blog-rubric/SKILL.md`

- [ ] **Step 1: Add a "See also" section near the top**

Insert this block right after the H1 (line 6) of `.claude/skills/firstmovers-blog-rubric/SKILL.md`:

```markdown
> **See also (sibling skills — load these for the relevant phase):**
> - `fm-prose-generation` — the **method** to write a body that hits this rubric
> - `fm-wordpress-push` — pushing a validated draft to WP
> - `fm-ahrefs` / `fm-gsc` / `fm-ga4` / `fm-searchable` — discovery
> - `fm-cannibalization` — the gate that runs before discovery and again before assembly
> - `fm-clickup-ops` — the human-loop surface
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/firstmovers-blog-rubric/SKILL.md
git commit -m "docs(skills): link rubric to sibling fm-* process skills"
```

---

## Phase 3 — Discovery Tooling Verification for /loop

> **Why this phase exists.** The discover modules (`tools/discover/gsc.py`, `tools/discover/ga4_gap.py`, `tools/discover/searchable_aeo.py`) were written when GSC/GA4/Searchable weren't actually being called by the production routine — they handled hypothetical response shapes. Now that `/loop` will call them for real, we verify each module against the actual MCP/SDK response payload and lock the behavior with a test.

### Task 14: Add integration test fixture for GSC adapter

**Files:**
- Create: `tests/test_discover_gsc.py`
- Create: `tests/fixtures/gsc_response.json`

- [ ] **Step 1: Capture a real `mcp__gsc__get_search_analytics` response**

On the VM (or any machine with GSC access), run:

```python
import json
resp = mcp__gsc__get_search_analytics(
    site_url="https://firstmovers.ai/",
    start_date="2026-04-14",
    end_date="2026-05-11",
    dimensions=["query", "page"],
    row_limit=50,
)
with open("tests/fixtures/gsc_response.json", "w") as f:
    json.dump(resp, f, indent=2)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_discover_gsc.py
import json
from pathlib import Path

import pytest

from tools.discover.gsc import discover
from tools.inventory import load as load_inventory


@pytest.fixture
def gsc_response():
    return json.loads(Path("tests/fixtures/gsc_response.json").read_text())


@pytest.fixture
def inventory():
    return load_inventory()


def test_gsc_discover_returns_candidates(gsc_response, inventory):
    """Verify discover handles the actual GSC response shape and returns ≥1 striking-distance candidate."""
    cands = discover(gsc_response, inventory)
    assert isinstance(cands, list)
    assert len(cands) >= 1
    for c in cands:
        assert c.focus_keyword
        assert c.discovery_source == "gsc-striking-distance"
        assert c.discovery_evidence
        assert 4 <= c.discovery_evidence["position"] <= 15


def test_gsc_discover_filters_existing_winners(gsc_response, inventory):
    """Queries the site already ranks 1-3 for must not appear as striking-distance candidates."""
    cands = discover(gsc_response, inventory)
    for c in cands:
        assert c.discovery_evidence["position"] >= 4
```

- [ ] **Step 3: Run the test to verify it fails or passes meaningfully**

```bash
pytest tests/test_discover_gsc.py -v
```

Expected: PASS if the fixture matches the current adapter, FAIL with a clear error if the response shape drifted. If FAIL, fix `tools/discover/gsc.py` minimally to match the real shape.

- [ ] **Step 4: Commit**

```bash
git add tests/test_discover_gsc.py tests/fixtures/gsc_response.json tools/discover/gsc.py
git commit -m "test(discover): lock GSC adapter against real response fixture"
```

### Task 15: Add integration test for GA4 adapter

**Files:**
- Create: `tests/test_discover_ga4.py`
- Create: `tests/fixtures/ga4_rows.json`

- [ ] **Step 1: Capture a real `tools.ga4.run_report` response**

```python
import json
from tools.ga4 import run_report

rows = run_report(
    property_id="<GA4_PROPERTY_ID>",
    dimensions=["pagePath"],
    metrics=["sessions", "engagedSessions"],
    date_ranges=[
        {"start_date": "29daysAgo", "end_date": "yesterday"},
        {"start_date": "57daysAgo", "end_date": "30daysAgo"},
    ],
    limit=50,
)
with open("tests/fixtures/ga4_rows.json", "w") as f:
    json.dump(rows, f, indent=2, default=str)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_discover_ga4.py
import json
from pathlib import Path

import pytest

from tools.discover.ga4_gap import discover
from tools.inventory import load as load_inventory


@pytest.fixture
def ga4_rows():
    return json.loads(Path("tests/fixtures/ga4_rows.json").read_text())


@pytest.fixture
def inventory():
    return load_inventory()


def test_ga4_discover_identifies_decay(ga4_rows, inventory):
    cands = discover(ga4_rows, inventory)
    assert isinstance(cands, list)
    for c in cands:
        assert c.discovery_source == "ga4-decay"
        ev = c.discovery_evidence
        assert ev["last_28d_sessions"] < ev["prior_28d_sessions"] * 0.6
        assert ev["prior_28d_sessions"] >= 50


def test_ga4_discover_excludes_non_inventory_paths(ga4_rows, inventory):
    cands = discover(ga4_rows, inventory)
    inv_paths = {entry.url_path for entry in inventory.entries}
    for c in cands:
        assert c.discovery_evidence["page_path"] in inv_paths
```

- [ ] **Step 3: Run the test**

```bash
pytest tests/test_discover_ga4.py -v
```

Expected: PASS, or FAIL with a clear gap that's quick to fix in `tools/discover/ga4_gap.py`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_discover_ga4.py tests/fixtures/ga4_rows.json tools/discover/ga4_gap.py
git commit -m "test(discover): lock GA4 decay adapter against real fixture"
```

### Task 16: Add integration test for Searchable adapter

**Files:**
- Create: `tests/test_discover_searchable.py`
- Create: `tests/fixtures/searchable_visibility.json`

- [ ] **Step 1: Capture a real Searchable response**

```python
import json
resp = mcp__claude_ai_searchable__get_visibility_by_topic(project_id="<your-project-id>")
with open("tests/fixtures/searchable_visibility.json", "w") as f:
    json.dump(resp, f, indent=2)
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_discover_searchable.py
import json
from pathlib import Path

import pytest

from tools.discover.searchable_aeo import discover
from tools.inventory import load as load_inventory


@pytest.fixture
def searchable_resp():
    return json.loads(Path("tests/fixtures/searchable_visibility.json").read_text())


@pytest.fixture
def inventory():
    return load_inventory()


def test_searchable_discover_returns_aeo_candidates(searchable_resp, inventory):
    cands = discover(searchable_resp, inventory)
    assert isinstance(cands, list)
    for c in cands:
        assert c.discovery_source == "searchable-aeo"
        assert c.discovery_evidence
```

- [ ] **Step 3: Run the test**

```bash
pytest tests/test_discover_searchable.py -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_discover_searchable.py tests/fixtures/searchable_visibility.json tools/discover/searchable_aeo.py
git commit -m "test(discover): lock Searchable AEO adapter against real fixture"
```

---

## Phase 3.5 — Dual-mode idempotency (added during eng review)

> **Why this exists.** During the 7-day dual-mode cutover, both the old /schedule routine and the new /loop fire on the same day. The state file in `data/runs/_daily/<DATE>.json` lives on the operator's local disk; the cloud /schedule routine cannot see it. Without a second idempotency signal, both can emit a daily task on the same day. Solution: query ClickUp before emitting and short-circuit if a task tagged `fm-content-daily` already exists for today.

### Task 16.5: Add ClickUp-side idempotency check to tools/daily.py

**Files:**
- Modify: `tools/daily.py`
- Create: `tests/test_daily_clickup_idempotency.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_daily_clickup_idempotency.py
from unittest.mock import MagicMock
from tools.daily import should_skip_for_clickup_dup


def test_skip_when_clickup_task_exists_for_today():
    """When ClickUp already has a task tagged fm-content-daily for today, skip emit."""
    fake_clickup_search = MagicMock(return_value={
        "tasks": [
            {"id": "abc123", "name": "[2026-05-12] AI consulting ROI for mid-market",
             "tags": [{"name": "fm-content-daily"}]},
        ],
    })
    skip, task_id = should_skip_for_clickup_dup(
        today="2026-05-12", clickup_search_fn=fake_clickup_search,
    )
    assert skip is True
    assert task_id == "abc123"


def test_no_skip_when_no_clickup_task_for_today():
    fake_clickup_search = MagicMock(return_value={"tasks": []})
    skip, task_id = should_skip_for_clickup_dup(
        today="2026-05-12", clickup_search_fn=fake_clickup_search,
    )
    assert skip is False
    assert task_id is None


def test_no_skip_when_clickup_task_for_different_day():
    fake_clickup_search = MagicMock(return_value={
        "tasks": [
            {"id": "abc123", "name": "[2026-05-11] Yesterday's idea",
             "tags": [{"name": "fm-content-daily"}]},
        ],
    })
    skip, task_id = should_skip_for_clickup_dup(
        today="2026-05-12", clickup_search_fn=fake_clickup_search,
    )
    assert skip is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_daily_clickup_idempotency.py -v
```

Expected: FAIL with `AttributeError: module 'tools.daily' has no attribute 'should_skip_for_clickup_dup'`.

- [ ] **Step 3: Implement should_skip_for_clickup_dup**

Append to `tools/daily.py`:

```python
def should_skip_for_clickup_dup(today: str, clickup_search_fn) -> tuple[bool, str | None]:
    """Check ClickUp for an existing daily-idea task for `today`.

    Returns (skip, task_id). If a task tagged 'fm-content-daily' with name
    starting [<today>] exists, returns (True, task_id) so the caller can
    mirror that task_id into local state instead of emitting a duplicate.

    Used during the dual-mode cutover window where /schedule and /loop may
    both fire on the same day.
    """
    prefix = f"[{today}]"
    resp = clickup_search_fn(
        list_id="901326229295",
        tags=["fm-content-daily"],
        order_by="created",
        reverse=True,
        limit=5,
    )
    for task in resp.get("tasks", []):
        if task.get("name", "").startswith(prefix):
            tag_names = {t.get("name") for t in task.get("tags", [])}
            if "fm-content-daily" in tag_names:
                return True, task.get("id")
    return False, None
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_daily_clickup_idempotency.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Wire into the daily-idea workflow (in workflows/content-daily-idea-loop.md Step 1)**

After the state-file idempotency check, add:

```python
# ClickUp-side idempotency (dual-mode safety; remove after cutover window)
from tools.daily import should_skip_for_clickup_dup
skip, existing_task_id = should_skip_for_clickup_dup(
    today=today, clickup_search_fn=clickup_search,
)
if skip:
    # mirror the cloud-emitted task into local state so polling-drafter picks it up
    Skill(skill="fm-clickup-ops")
    resp = clickup_get_task(task_id=existing_task_id, detail_level="summary")
    # reconstruct minimal proposal from task description; persist as emitted state
    state = DailyState(date=today, proposal=<parsed proposal>)
    state = mark_emitted(state, task_id=existing_task_id)
    save_state(state)
    clickup_create_task_comment(
        task_id="86ah3ywyh",
        comment_text=f"Daily idea {today}: cloud routine already emitted task {existing_task_id}; mirrored to local state.",
    )
    sys.exit(0)
```

- [ ] **Step 6: Commit**

```bash
git add tools/daily.py tests/test_daily_clickup_idempotency.py
git commit -m "feat(daily): ClickUp-side idempotency for dual-mode cutover safety"
```

---

## Phase 4 — Daily-idea /loop Migration

### Task 17: Write workflows/content-daily-idea-loop.md

**Files:**
- Create: `workflows/content-daily-idea-loop.md`

- [ ] **Step 1: Write the /loop variant workflow**

```markdown
# Daily idea — /loop variant (runs on VM, all 4 discovery sources)

> **Goal.** Once per day at 07:00 Phoenix, post ONE blog topic to ClickUp for Nikki to approve. Uses all 4 discovery sources (Ahrefs gap + GSC striking-distance + GA4 decay + Searchable AEO).

> **Runtime.** `/loop "0 14 * * *" "<this prompt>"` on the VM. Phoenix is UTC-7 year-round, so 14:00 UTC = 07:00 Phoenix.

> **Why /loop not /schedule.** Three of the four discovery sources (GSC, GA4, Searchable) are not reachable from the /schedule sandbox proxy. The /loop runs in a local Claude Code session on the VM where all local MCPs work.

---

## Inputs

- Today's Phoenix date (state file is keyed by Phoenix date)
- Inventory snapshot at `data/inventory/firstmovers-ai.json` — must be fresh (≤7 days old)

If inventory is stale, refresh first per `workflows/content-inventory-refresh.md`.

---

## Step-by-step

### 1. Canary + idempotency

```python
import sys; sys.path.insert(0, ".")
from tools.daily import DAILY_DIR, load_state
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.now(ZoneInfo("America/Phoenix")).strftime("%Y-%m-%d")
state_path = DAILY_DIR / f"{today}.json"
if state_path.exists():
    # idempotent skip
    Skill(skill="fm-clickup-ops")
    clickup_create_task_comment(
        task_id="86ah3ywyh",
        comment_text=f"Daily idea {today}: already emitted, skipping.",
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

### 4. Pull all 4 discovery signals (parallel where possible)

```python
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.now(ZoneInfo("America/Phoenix")).strftime("%Y-%m-%d")
dow = datetime.now(ZoneInfo("America/Phoenix")).strftime("%A")

competitor = {
    "Monday": "mckinsey.com", "Tuesday": "bcg.com", "Wednesday": "bain.com",
    "Thursday": "hubspot.com", "Friday": "accenture.com", "Saturday": "deloitte.com",
    "Sunday": "mckinsey.com",
}[dow]

# Ahrefs gap (competitor rotation)
ahrefs_resp = mcp__ahrefs__site-explorer-organic-keywords(
    target=competitor, mode="subdomains", date=today,
    limit=100, order_by="sum_traffic:desc",
    select="keyword,best_position,best_position_url,sum_traffic,volume,keyword_difficulty",
)

# GSC striking distance
gsc_resp = mcp__gsc__get_search_analytics(
    site_url="https://firstmovers.ai/",
    start_date="<today minus 28 days>",
    end_date=today,
    dimensions=["query", "page"],
    row_limit=500,
    data_state="final",
)

# GA4 decay
from tools.ga4 import run_report
ga4_rows = run_report(
    property_id="<GA4_PROPERTY_ID from .env>",
    dimensions=["pagePath"],
    metrics=["sessions", "engagedSessions"],
    date_ranges=[
        {"start_date": "29daysAgo", "end_date": "yesterday"},
        {"start_date": "57daysAgo", "end_date": "30daysAgo"},
    ],
    limit=500,
)

# Searchable AEO
searchable_resp = mcp__claude_ai_searchable__get_visibility_by_topic(
    project_id="<from tools.identities>",
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
from tools.daily import pick_top_candidate, candidate_to_proposal_dict, DailyState, save_state, mark_emitted

inv = load()
inv.assert_fresh()
inv.assert_complete()

translated = [{"keyword": kw["keyword"], "position": kw.get("best_position"),
               "traffic": kw.get("sum_traffic", 0), "volume": kw.get("volume", 0),
               "kd": kw.get("keyword_difficulty", 0),
               "best_url": kw.get("best_position_url")}
              for kw in ahrefs_resp["keywords"]]

candidates = []
candidates.extend(ahrefs_discover(competitor, {"keywords": translated}, inv))
candidates.extend(gsc_discover(gsc_resp, inv))
candidates.extend(ga4_discover(ga4_rows, inv))
candidates.extend(searchable_discover(searchable_resp, inv))

# Cannibalization filter
clear = [
    c for c in candidates
    if evaluate(ProposedTopic(focus_keyword=c.focus_keyword, working_title=c.working_title,
                              audience=c.audience, category_id=c.category_id), inv).severity
       not in ("critical", "high")
]

top = pick_top_candidate(clear)
if top is None:
    clickup_create_task_comment(task_id="86ah3ywyh",
        comment_text=f"Daily idea {today}: no clear candidates after cannibalization (out of {len(candidates)} raw).")
    sys.exit(0)
```

### 6. Generate working title + outline (Claude in this loop's context)

Generate:
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
    list_id="901326229295",
    name=f"[{today}] {proposal['working_title']}",
    markdown_description=<rich block with focus_kw, audience, evidence, top SERP results>,
    assignees=[26221739],
    due_date=today,
    tags=["fm-content-daily"],
)
state = mark_emitted(state, task_id=resp.get("task_id") or resp.get("id"))
save_state(state)
```

### 8. Status comment + commit

```python
clickup_create_task_comment(
    task_id="86ah3ywyh",
    comment_text=f"Daily idea {today}: emitted '{proposal['working_title']}' from "
                 f"{top.discovery_source} (task {state.clickup_task_id}).",
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

- Any single discovery source failing: log + continue with remaining sources (do not abort)
- All 4 sources failing: comment failure on 86ah3ywyh, exit non-zero, /loop will retry next interval
- Inventory stale: comment + exit non-zero (operator refreshes)
- Cannibalization gate refuses to run on degraded entries: same as above

## Idempotency

State file `data/runs/_daily/<TODAY>.json` is the lock. If it exists, the routine is a no-op. This means a /loop run AND a stale /schedule run on the same day cannot double-post.
```

- [ ] **Step 2: Commit**

```bash
git add workflows/content-daily-idea-loop.md
git commit -m "feat(workflows): /loop variant of daily-idea using all 4 discovery sources"
```

### Task 18: Register the /loop in operator's local Claude Code session

**Files:** none (operator action — local Windows Claude Code session)

- [ ] **Step 1: In the operator's open Claude Code session, register the /loop**

```
/loop "0 14 * * *" "FM-Content daily-idea /loop. Full SOP: workflows/content-daily-idea-loop.md (READ THIS FIRST and follow it exactly)."
```

- [ ] **Step 2: Verify registration**

```
/loop list
```

Expected: one entry with cron `0 14 * * *`, prompt referencing the workflow.

- [ ] **Step 3: Trigger one manual run**

```
/loop run <id>
```

Expected: ClickUp task appears in list `901326229295` assigned to Nikki with today's date in the name; state file written to `data/runs/_daily/<today>.json`; comment posted on `86ah3ywyh`.

- [ ] **Step 4: Verify state file**

```powershell
Get-Content data\runs\_daily\$((Get-Date -Format 'yyyy-MM-dd')).json
```

Expected: JSON with `discovery_source`, `discovery_evidence`, `working_title`, `clickup_task_id`, state `emitted`.

### Task 19: Live-fire smoke test (wait for the next 14:00 UTC tick with Claude Code open)

**Files:** none

- [ ] **Step 1: Keep Claude Code open through the next 14:00 UTC / 07:00 Phoenix tick**

Operator note: if Claude Code is closed at fire time, the /loop will not fire. The heartbeat (Phase 6) detects this and alerts.

- [ ] **Step 2: After the tick, verify state file**

```powershell
Get-ChildItem data\runs\_daily\ | Sort-Object LastWriteTime -Descending | Select-Object -First 3
```

Expected: new file for today's date with mtime within 5 minutes of 14:00 UTC.

- [ ] **Step 3: Verify ClickUp task created**

In ClickUp UI, confirm a new task in the Content Projects list assigned to Nikki, tagged `fm-content-daily`.

- [ ] **Step 4: Note any issues + fix**

If failures, check the Claude Code conversation transcript for the trace; fix in `workflows/content-daily-idea-loop.md` or `tools/discover/*` as needed.

---

## Phase 5 — Polling-drafter /loop Migration

### Task 20: Write workflows/content-poll-and-draft-loop.md

**Files:**
- Create: `workflows/content-poll-and-draft-loop.md`

- [ ] **Step 1: Write the /loop variant**

```markdown
# Polling drafter — /loop variant (runs on VM)

> **Goal.** Every 3 hours, check daily-state files for ClickUp tasks Nikki has marked done. For each newly-approved one: re-run cannibalization, fetch SERP, generate prose, validate via rubric, push to WordPress as draft.

> **Runtime.** `/loop "0 */3 * * *" "<this prompt>"` on the VM.

> **Why /loop.** Same reason as daily-idea. The local Ahrefs, WordPress, and ClickUp connectors work here; future enhancements (e.g., GSC "is this query already winning?" pre-draft sanity check) require local MCP access.

---

## Step-by-step

### 1. List pending work (silent if empty)

```python
import sys; sys.path.insert(0, ".")
from tools.daily import pending_approvals, pending_drafts

awaiting = pending_approvals()
drafts = pending_drafts()
if not awaiting and not drafts:
    sys.exit(0)
```

### 2. Canary

```
Skill(skill="fm-clickup-ops")
clickup_create_task_comment(task_id="86ah3ywyh",
    comment_text=f"Routine fm-content-poll-and-draft started at <iso-now>")
```

### 3. Process each pending approval

```python
from tools.daily import is_task_approved, mark_approved, save_state

for state in pending_approvals():
    resp = clickup_get_task(task_id=state.clickup_task_id, detail_level="summary")
    approved, status_name = is_task_approved(resp)
    if approved:
        mark_approved(state, status_name=status_name)
        save_state(state)
```

### 4. Process each pending draft

```
Skill(skill="firstmovers-blog-rubric")
Skill(skill="fm-prose-generation")
Skill(skill="fm-cannibalization")
Skill(skill="fm-wordpress-push")
```

For each pending draft:

```python
from tools.slate import SlateProposal
from tools.draft import prepare_brief, assemble
from tools.inventory import load
from tools.rubric import FaqItem, RubricViolation
from tools.push_wp import build_create_payload
from tools.rank_math import build_meta
from tools.daily import mark_drafted

inv = load(); inv.assert_fresh(); inv.assert_complete()

for state in pending_drafts():
    prop = SlateProposal(**state.proposal)
    brief = prepare_brief(prop, inv)   # cannibalization defense-in-depth re-check

    serp = mcp__ahrefs__serp-overview(
        keyword=prop.focus_keyword, country="us", top_positions=10,
        select="title,url,position,domain_rating,backlinks,traffic,top_keyword",
    )

    # Generate body_html, faq_items, seo_title, meta_description per fm-prose-generation
    body_html = "..."   # 2500-3500 words
    faq_items = [FaqItem(question="...", answer="...") for _ in range(5)]
    seo_title = "..."   # ≤60 chars
    meta_description = "..."   # ≤155 chars

    # Validate + retry up to 2x
    for attempt in range(3):
        try:
            assembled = assemble(brief, body_html=body_html, faq_items=faq_items,
                                 seo_title=seo_title, meta_description=meta_description)
            break
        except RubricViolation as e:
            if attempt == 2:
                clickup_create_task_comment(
                    task_id=state.clickup_task_id,
                    comment_text=f"Rubric violation after 3 attempts: {e}. Skipping until next poll.",
                )
                continue
            # regenerate prose addressing the named rule

    # Push to WP
    payload = build_create_payload(
        title=assembled.title, content=assembled.body_html, slug=assembled.slug,
        excerpt=assembled.excerpt, category_id=assembled.category_id,
    )
    wp = wp_create_post(title=payload.title, content=payload.content,
                       excerpt=payload.excerpt, slug=payload.slug, status="draft",
                       categories=payload.categories, post_author=3)
    post_id = int(wp["id"])

    # Rank Math meta
    rm = build_meta(focus_keyword=assembled.focus_keyword, seo_title=assembled.seo_title,
                    meta_description=assembled.meta_description, slug=assembled.slug)
    for key, value in [
        ("rank_math_focus_keyword", rm.focus_keyword),
        ("rank_math_title", rm.seo_title),
        ("rank_math_description", rm.meta_description),
    ]:
        wp_update_post_meta(post_id=post_id, key=key, value=value)

    edit_url = f"https://firstmovers.ai/wp-admin/post.php?post={post_id}&action=edit"
    mark_drafted(state, post_id=post_id, edit_url=edit_url)
    save_state(state)

    wc = len(assembled.body_html.split())
    clickup_create_task_comment(
        task_id=state.clickup_task_id,
        comment_text=(
            f"Drafted to WordPress.\n\n"
            f"- Edit: {edit_url}\n"
            f"- Preview: https://firstmovers.ai/?p={post_id}&preview=true\n"
            f"- Word count: {wc:,}\n"
            f"- Author: Josh McCoy (post_author=3)\n\n"
            f"Nikki: review, set slug if needed ({assembled.slug}), add featured image, "
            f"get Josh CTA approval, publish, NitroPack purge."
        ),
    )
```

### 5. Status comment on 86ah3ywyh

```python
clickup_create_task_comment(
    task_id="86ah3ywyh",
    comment_text=f"Polling drafter run: {len([s for s in pending_approvals_at_start if s.is_approved])} newly approved, "
                 f"{drafted_count} drafted, {still_awaiting} still awaiting.",
)
```

### 6. Commit + push

```python
import subprocess
subprocess.run(["git", "add", "data/runs/_daily/"], check=False)
subprocess.run(["git", "commit", "-m", "chore(daily): polling-drafter advance"], check=False)
subprocess.run(["git", "push"], check=False)
```

## Failure handling

- **CannibalizationError on `prepare_brief`**: comment on the ClickUp task, skip draft, leave state at `approved`. Operator must reconcile.
- **RubricViolation × 3**: comment, skip until next poll.
- **WAF block on `wp_create_post`**: queue to `data/runs/_pending-push/` via `tools.push_wp.queue_for_path_b`, trigger `wp-push-fallback.yml` via `gh` CLI. Leave state at `approved`.
- **GA4/GSC failure (not used here directly)**: N/A — polling-drafter doesn't call discovery MCPs.

## Idempotency

- State `drafted` (wp_post_id set) → silent skip
- State `pending` (no clickup_task_id) → silent skip (daily-idea handles it)
```

- [ ] **Step 2: Commit**

```bash
git add workflows/content-poll-and-draft-loop.md
git commit -m "feat(workflows): /loop variant of polling drafter"
```

### Task 21: Register polling-drafter /loop

**Files:** none (operator action — local Claude Code session)

- [ ] **Step 1: In the same operator Claude Code session**

```
/loop "0 */3 * * *" "FM-Content polling-drafter /loop. Full SOP: workflows/content-poll-and-draft-loop.md (READ THIS FIRST and follow it exactly)."
```

- [ ] **Step 2: Verify list**

```
/loop list
```

Expected: two entries — daily-idea cron `0 14 * * *` and polling-drafter cron `0 */3 * * *`.

### Task 22: End-to-end smoke test

**Files:** none

- [ ] **Step 1: Wait for next daily-idea fire, get a task into ClickUp**

After the next 07:00 Phoenix, verify a task lands in Content Projects.

- [ ] **Step 2: Manually mark that task done in ClickUp**

In ClickUp UI, change status to "done" or "complete".

- [ ] **Step 3: Wait up to 3 hours for polling-drafter to fire**

Or trigger manually: `/loop run <polling-drafter-id>`.

- [ ] **Step 4: Verify WP draft was created**

Check WP admin at https://firstmovers.ai/wp-admin/ — new draft, post_author=Josh, Rank Math meta populated.

- [ ] **Step 5: Verify state file shows `drafted`**

```bash
cat data/runs/_daily/<that-date>.json | python -m json.tool
```

Expected: `wp_post_id` field populated, state advanced to `drafted`.

---

## Phase 6 — /schedule Heartbeat Reduction

### Task 23: Write workflows/heartbeat-canary.md

**Files:**
- Create: `workflows/heartbeat-canary.md`

- [ ] **Step 1: Write the heartbeat workflow**

```markdown
# Heartbeat canary — /schedule safety net

> **Goal.** If the /loop is not firing (operator's Claude Code is closed, Windows is asleep, machine is off, or future-VM is down), this /schedule routine still fires from claude.ai cloud and pings the ClickUp pipeline status task. Aditya notices, restarts whatever needs restarting.

> **Cron.** `0 */12 * * *` UTC (every 12 hours: 00:00 and 12:00 UTC).

> **Why.** /loop runs in the operator's local Claude Code session. If that session is closed, no /loop fires and no errors surface. This heartbeat is the independent canary. Especially important in the local-first phase where the workstation is NOT always-on.

## What it does (minimal — no MCPs other than ClickUp)

1. Read latest entry in `data/runs/_daily/` (via the FirstMoversWP MCP repo content, or just check ClickUp activity)
2. Compute time-since-last-emit
3. If > 36h since last emit → alert on `86ah3ywyh` (the VM is down or /loop misfired)
4. Otherwise → silent (or single-line "ok" every 24h)

## Implementation note

Since /schedule cloud routines can't read local files, the heartbeat reads its signal from ClickUp itself: list the most recent task tagged `fm-content-daily` in list `901326229295`, look at `date_created`. If older than 36h, alert.

## Prompt

    FM-Content heartbeat canary routine. Runs every 12 hours.

    1. List tasks in list 901326229295 tagged 'fm-content-daily':
       resp = clickup_search(...)  # filter by tag, order by created desc, limit 1

    2. If list empty: comment on 86ah3ywyh: "Heartbeat: no daily-idea tasks found in last 7 days. /loop VM may be offline." and exit.

    3. If most-recent task's date_created > 36 hours ago: comment on 86ah3ywyh: "Heartbeat alert: last daily-idea task was <X> hours ago. Expected every 24h. /loop VM may be offline."

    4. Otherwise: exit silently (or comment once per day with "ok" at 12:00 UTC only).

## Failure handling

This routine is intentionally minimal. It only needs the ClickUp connector. If even this fails, the operator should investigate the ClickUp connector itself.
```

- [ ] **Step 2: Commit**

```bash
git add workflows/heartbeat-canary.md
git commit -m "feat(workflows): /schedule heartbeat canary as VM-down safety net"
```

### Task 24: Disable old /schedule routines

**Files:** none (operator action)

- [ ] **Step 1: Pre-disable verification**

Run `/schedule list` and confirm the two existing routines (`fm-content-daily-idea`, `fm-content-poll-and-draft`) are still listed with cron schedules.

- [ ] **Step 2: Run dual-mode for 7 days FIRST**

**DO NOT disable yet.** For 7 days, both /loop and the original /schedule routines run. The state-file idempotency guarantees no double-post. This is the safety-net window for catching /loop issues.

Track in a spreadsheet or notes file: each day, confirm /loop fired AND /schedule fired AND only one task was emitted per day.

- [ ] **Step 3: After 7 successful days, disable**

```
/schedule update fm-content-daily-idea       enabled=false
/schedule update fm-content-poll-and-draft   enabled=false
```

- [ ] **Step 4: Confirm disabled**

```
/schedule list
```

Expected: both routines listed with `enabled: false`.

### Task 25: Register heartbeat /schedule routine

**Files:** none (operator action)

- [ ] **Step 1: Register**

```
/schedule create
  name=fm-content-heartbeat
  cron="0 */12 * * *"
  model=claude-sonnet-4-6
  prompt="<contents of workflows/heartbeat-canary.md::Prompt section>"
  mcp_connections=[ClickUp]
```

- [ ] **Step 2: Trigger once manually + verify**

```
/schedule run fm-content-heartbeat
```

Expected: silent (assuming /loop is running normally), or alert comment on `86ah3ywyh` if /loop is misbehaving.

- [ ] **Step 3: Simulate failure to test alert path**

Temporarily stop the systemd unit on VM: `sudo systemctl stop fm-content-loop`. Wait until the next heartbeat tick (or run manually). Expected: alert comment posted to `86ah3ywyh`. Then restart: `sudo systemctl start fm-content-loop`.

---

## Phase 7 — Documentation + Cutover Verification

### Task 26: Update CLAUDE.md flow table

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Replace the "## The flow" table**

In `CLAUDE.md`, replace the existing "The flow" table (currently 4 rows for Sunday/Wednesday cycle with /schedule routines) with:

```markdown
## The flow (hybrid /loop local + /schedule heartbeat)

| Day (Phoenix UTC-7) | Job | Runtime | What happens |
|---|---|---|---|
| Every day 07:00 | daily-idea | `/loop` in operator's Claude Code | All 4 discovery sources → cannibalization → 1 ClickUp task for Nikki |
| Sun-Sat (continuous) | (Nikki) | manual | Mark approved tasks "done" in ClickUp |
| Every 3 hours | polling-drafter | `/loop` in operator's Claude Code | Detect approvals → SERP + prose + rubric → push WP draft |
| Every 12 hours | heartbeat | `/schedule` cloud | If no daily-idea task in last 36h, alert on 86ah3ywyh |
| Wed-Sun | (Nikki) | manual | Polish in WP, get Josh CTA approval, publish |

Phoenix is fixed offset UTC-7 year-round. No DST.

Runtime note: /loop fires only when the operator's Claude Code session is open. A future plan will move /loop to an always-on VM. For now, the heartbeat catches gaps.
```

- [ ] **Step 2: Update the MCP map table**

In the same file, update the MCP map row for `analytics-mcp` and add rows for `gsc`, `searchable`, `airtable`, `elementor`:

```markdown
| `mcp__gsc__*` | Striking-distance discovery (/loop only — no claude.ai connector) | `get_search_analytics`, `get_search_by_page_query` |
| `mcp__analytics-mcp__*` | (hangs — use `tools.ga4` direct SDK) | n/a |
| `mcp__claude_ai_searchable__*` | AEO discovery | `get_visibility_by_prompt`, `get_visibility_by_topic`, `get_visibility_summary` |
| `mcp__airtable__*` | Inventory side-table (optional) | `list_records`, `update_records` |
| `mcp__firstmovers-elementor__*` | Page-level Elementor edits (NOT for blog posts) | `get_page`, `update_page` |
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE): switch flow table to hybrid /loop + /schedule heartbeat"
```

### Task 27: Update workflows/schedule-registration.md

**Files:**
- Modify: `workflows/schedule-registration.md`

- [ ] **Step 1: Add deprecation banner at top**

Insert after line 4 (after the existing `> Copy-paste invocations...` block):

```markdown
> **DEPRECATED for production (2026-05-12).** The two routines documented below are kept for backstop use only. Production flow has migrated to /loop on the VM:
>
> - `workflows/content-daily-idea-loop.md`
> - `workflows/content-poll-and-draft-loop.md`
> - `workflows/heartbeat-canary.md` (the one /schedule routine still in use)
>
> This file remains for reference and for the 7-day dual-mode cutover window.
```

- [ ] **Step 2: Commit**

```bash
git add workflows/schedule-registration.md
git commit -m "docs(workflows): deprecate /schedule routines in favor of /loop hybrid"
```

### Task 28: 7-day dual-mode observation log

**Files:**
- Create: `docs/migration/2026-05-12-loop-cutover-log.md`

- [ ] **Step 1: Create the log skeleton**

```markdown
# /loop migration cutover log

> Track daily over 7 days to validate the /loop runtime before disabling /schedule routines.

| Date | /loop daily fired? | /schedule daily fired? | /loop polling fired? | Tasks emitted (should be 1/day) | WP drafts pushed | Notes |
|---|---|---|---|---|---|---|
| 2026-05-13 | | | | | | |
| 2026-05-14 | | | | | | |
| 2026-05-15 | | | | | | |
| 2026-05-16 | | | | | | |
| 2026-05-17 | | | | | | |
| 2026-05-18 | | | | | | |
| 2026-05-19 | | | | | | |

## Pass criteria (to disable /schedule)

- 7 consecutive days where /loop fires and emits exactly 1 daily task
- At least 3 successful end-to-end runs (idea → approval → WP draft)
- Zero double-emissions (state-file idempotency holds)
- Heartbeat fires every 12h without spurious alerts

## Issues observed

(append as encountered)
```

- [ ] **Step 2: Commit**

```bash
git add docs/migration/2026-05-12-loop-cutover-log.md
git commit -m "docs(migration): /loop cutover observation log"
```

- [ ] **Step 3: Operator fills in daily over 7 days**

Each day at end-of-day, check the four columns and record. On day 7, decide: pass (disable /schedule routines per Task 24 step 3) or extend.

---

## Self-Review

**1. Spec coverage:**
- VM provisioning → Phase 0 (Tasks 1-4)
- 8 skill files → Phases 1-2 (Tasks 5-13)
- Discovery tool verification → Phase 3 (Tasks 14-16)
- Daily-idea /loop → Phase 4 (Tasks 17-19)
- Polling-drafter /loop → Phase 5 (Tasks 20-22)
- /schedule heartbeat reduction → Phase 6 (Tasks 23-25)
- Documentation + safety-net cutover → Phase 7 (Tasks 26-28)

All user requirements covered: VM hosting decision, both routines migrated, safety-net heartbeat retained, 8 skills created.

**2. Placeholder scan:** Three justified placeholders flagged for human action:
- `<repo-url>`, `<vm-host>`, `<your-project-id>`, `<GA4_PROPERTY_ID>` — operator-supplied infrastructure values
- `<today minus 28 days>` in discovery code — should be computed via `(date.today() - timedelta(days=28)).isoformat()` at runtime; noted in the workflow text
- Prose generation steps use `body_html = "..."` — by design, the prose is what the agent generates; the skill `fm-prose-generation` is the actual instruction set

**3. Type consistency:**
- `SlateProposal`, `DailyState`, `ProposedTopic`, `RubricViolation`, `CannibalizationError`, `FaqItem`, `AssembledDraft` — all imported from the same module paths as used in the existing `workflows/content-poll-and-draft.md`. No type drift introduced.
- `is_task_approved`, `mark_emitted`, `mark_approved`, `mark_drafted`, `save_state`, `pending_approvals`, `pending_drafts` — all match `tools/daily.py` signatures referenced in existing workflows.
- `discovery_source`, `discovery_id`, `discovery_evidence` — mandatory fields per CLAUDE.md, used consistently.

---

## Execution Handoff

Plan complete and saved. Before offering execution choice, the user has explicitly requested `/plan-eng-review` next — running that against this plan before any code moves.
