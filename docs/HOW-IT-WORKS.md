# How It Works — A Walkthrough

> **Read this first.** This is the plain-language explainer for the content
> pipeline. It tells you what the system is, how it runs, and exactly what a
> client does in their Claude Code session to get it live. Once you have read
> this, the step-by-step checklist in [DEPLOYMENT-SOP.md](DEPLOYMENT-SOP.md)
> will make sense.

---

## 1. The big picture

This repo is an **automated blog-content engine**. Left running, it produces a
steady stream of search-optimized WordPress blog *drafts* for a human to review
and publish. It never publishes on its own — a person always has the final say.

It does three things on a schedule:

1. **Finds a topic** worth writing about — every day.
2. **Writes the draft** — whenever a human approves a topic.
3. **Watches itself** — and raises an alarm if it goes quiet.

The thing that makes it trustworthy is one rule: it will **never** propose a
topic that overlaps something the site has already published. That check (the
"cannibalization gate") is the core of the design.

### Why it is built in layers (the W80 model)

The system deliberately splits work between the AI and plain code:

| Layer | What it is | Who does it |
|---|---|---|
| **Workflows** | Markdown SOPs in `workflows/` — the instructions for each job | You read them |
| **Agent** | Claude, running in a Claude Code session | Reads the workflow, makes judgement calls, writes the prose |
| **Tools** | Python scripts in `tools/` — discovery, the cannibalization gate, the rubric, the WordPress push | Run deterministically, the same way every time |
| **Config** | `client_config.toml` — every client-specific value | You edit this once per client |

The AI handles the parts that need judgement (which topic is best, writing good
prose). The Python handles the parts that must be exact every time (the
cannibalization check, the quality rubric, the publish guardrails). That split
is why the output is reliable instead of "AI-ish."

---

## 2. How it runs — an always-on VPS

The pipeline runs on a small **always-on Linux VPS** (Hostinger). Understanding
this is the single most important thing in this document.

### The workhorse — system cron on the VPS

The three jobs (find-a-topic, write-the-draft, and a weekly inventory refresh)
are **system cron jobs on the VPS**. Cron is the operating system's own
scheduler — rock-solid, always running, and it survives reboots.

When a job is due, cron runs a small wrapper script
(`~/fm-content/scripts/run-job.sh`) that launches **headless Claude Code**
(`claude -p`). Claude reads that job's workflow file, executes it end to end,
and exits. The next tick is a brand-new, clean run.

Because the VPS is always on and cron is a system service, the jobs fire
reliably 24/7 with nobody watching — no app to keep open, no laptop, no
re-registration after a restart.

> **Why a VPS?** Three of the four topic-discovery sources (Google Search
> Console, GA4, Searchable) are only reachable from a real Claude Code
> environment, not the claude.ai cloud sandbox. Running Claude Code on the VPS
> unlocks all four sources *and* makes the schedule genuinely unattended. (An
> earlier version ran the jobs as `/loop`s inside a Claude Code session on
> someone's laptop — which stopped the moment the laptop slept. The always-on
> VPS replaced that.)

### The safety net — the `/schedule` heartbeat

There is one more, much smaller job: a **`/schedule` routine that runs in the
claude.ai cloud**, every 12 hours, completely independent of the VPS.

All it does is check: "has a new topic appeared in ClickUp in the last 36
hours?" If not, it posts an alert. It is the canary — if the VPS itself ever
goes down, the heartbeat is what tells the operator.

| | VPS cron (the workhorse) | `/schedule` heartbeat (the canary) |
|---|---|---|
| Runs where | The always-on VPS | claude.ai cloud |
| Runs when | On schedule, 24/7 | Every 12h |
| Does | The real work (discovery, drafting, inventory) | Only checks for silence + alerts |
| If the VPS is down | Stops | Keeps running, raises the alarm |

---

## 3. What the VPS needs

The VPS is a small always-on Linux box with Claude Code installed and signed
in. For the pipeline to work, it needs:

1. **The repo** — cloned from GitHub onto the VPS.
2. **The config filled in** — `client_config.toml` + `.env` (see §4).
3. **The MCP connections** — the client's own accounts connected:

   | Connection | Used for |
   |---|---|
   | WordPress | Reading the site's posts, pushing drafts |
   | Ahrefs | Competitor-gap discovery, SERP research |
   | Google Search Console | "Striking-distance" discovery |
   | Searchable | AI-engine (AEO) discovery |
   | ClickUp | Posting topics, reading approvals |

   GA4 does not use a connection — it reads a Google service-account key file
   instead. (And `analytics-mcp` is deliberately not used; it hangs.)

That is the whole dependency list. Airtable, n8n, and the page-builder
integrations are *not* part of this pipeline.

---

## 4. The setup, step by step (what actually happens)

Here is the full sequence a client (or the operator on their behalf) goes
through. The detailed checklist is in DEPLOYMENT-SOP.md; this is the narrative
so you understand *why* each step exists.

### Step 1 — Get the repo

Clone the GitHub repository onto the client's machine and open the folder in
Claude Code. Each client gets their **own** repo — the pipeline keeps state
files (which topics ran, the site inventory) on disk, and two clients must never
share that state.

### Step 2 — Fill in `client_config.toml`

This is the heart of the whole template. It is **one file** that holds every
value that differs between clients:

- the brand name and website URL,
- the WordPress author and valid blog categories,
- the ClickUp workspace, list, and the approver's user,
- the GSC / GA4 / Searchable targets,
- the weekly competitor rotation for gap analysis,
- the audience-to-CTA routing,
- and the schedule (what time the jobs fire, in which timezone).

Every Python file in `tools/` reads these values through one loader
(`tools/identities.py`). **You never edit a `.py` file to onboard a client.**
You edit this config, and the whole pipeline retargets itself.

> **The timezone subtlety.** The schedule is written as cron expressions in the
> *operator's* local timezone, because that is how the `/loop` engine reads
> them. The config has a worked example. Get this wrong and the job fires at
> the wrong hour — it is the most common setup mistake.

### Step 3 — Fill in `.env` (the secrets)

Copy `.env.example` to `.env` and paste in the secrets: the WordPress
application password, the Ahrefs API token, and the path to the GA4
service-account key. `.env` is never committed to git — secrets stay on the
client's machine only.

### Step 4 — Supply three content files

Three files hold *content* rather than configuration, so they need a human
touch per client:

- **`tools/external_links.py`** — the approved list of authoritative sites the
  blog is allowed to cite, by category.
- **`tools/internal_links.py`** — the client's own landing pages and blog URLs,
  so drafts can cross-link correctly.
- **`.claude/skills/<client>-blog-rubric/SKILL.md`** — the client's brand
  voice, tone, audience profile, and forbidden phrases.

### Step 5 — Connect the MCPs

In Claude Code, connect the client's WordPress, Ahrefs, GSC, Searchable, and
ClickUp accounts (see §3).

### Step 6 — Build the first inventory snapshot

Run the inventory builder once. It reads every post already on the client's
WordPress site and saves a snapshot. **This snapshot is what the cannibalization
gate compares against** — without it, the pipeline cannot run. The snapshot must
stay fresh (under 7 days old); a weekly `/loop` keeps it refreshed.

### Step 7 — Verify

Run the test suite and a manual dry run of each job. The checklist in
DEPLOYMENT-SOP.md §4 lists every box to tick.

### Step 8 — Stand up the VPS and install the cron jobs

Provision the always-on VPS, install the runtime (Claude Code + Python), clone
the repo, copy the secrets, and install the three system cron jobs (daily-idea,
polling-drafter, inventory-refresh) via the `run-job.sh` wrapper. Register the
heartbeat as a `/schedule` cloud routine. The full step-by-step is in
DEPLOYMENT-SOP.md. The pipeline is now live and runs unattended.

---

## 5. A day in the life — what runs, and what the human does

Once it is live, here is the rhythm:

```
  Every day, 07:00 (content timezone)
    └─ daily-idea cron job fires
         ├─ pulls 4 discovery sources (Ahrefs, GSC, GA4, Searchable)
         ├─ runs the cannibalization gate — drops any overlapping topic
         ├─ picks the single strongest surviving topic
         └─ posts ONE task to ClickUp, assigned to the approver

  Whenever the approver is ready (their own pace)
    └─ they open ClickUp, review the proposed topic,
       and mark the task "done" to approve it

  Every 3 hours
    └─ polling-drafter cron job fires
         ├─ checks each topic's ClickUp task for approval
         └─ for each newly-approved one:
              ├─ re-runs the cannibalization gate (defense in depth)
              ├─ researches the live search results
              ├─ writes the full draft (Claude, against the rubric)
              ├─ validates it against the quality rubric
              └─ pushes it to WordPress as a DRAFT

  Wednesday–Sunday
    └─ the human polishes the draft in WordPress,
       gets CTA sign-off, and publishes

  Every 12 hours (cloud)
    └─ heartbeat checks for silence and alerts if the loops stopped
```

The only recurring human action is **approving topics in ClickUp** and
**publishing finished drafts in WordPress**. Everything between those two
touch-points is automated.

---

## 6. The journey of one blog post

To make it concrete, follow a single post from idea to publish:

1. **Discovered.** At 07:00, daily-idea finds that a competitor ranks for a
   keyword the client does not. It survives the cannibalization gate.
2. **Proposed.** A ClickUp task appears: `[2026-05-20] <working title>`,
   assigned to the approver, with the evidence and the search data attached.
3. **Approved.** The approver reads it, agrees, and marks the task done.
4. **Drafted.** Within 3 hours, polling-drafter sees the approval, researches
   the live search results, and Claude writes a 2,500–3,500-word draft that
   passes the quality rubric (heading structure, internal/external links,
   FAQ schema, the right call-to-action for the audience).
5. **Pushed.** The draft lands in WordPress as `status=draft`, authored under
   the configured WordPress user. A ClickUp comment links to it.
6. **Published.** A human polishes it, adds a featured image, gets CTA
   sign-off, and hits publish.

At every step the state is recorded in a small JSON file
(`data/runs/_daily/<date>.json`), so the pipeline always knows where each post
is and never double-drafts.

---

## 7. The safety nets (why you can trust it)

| Guardrail | What it prevents |
|---|---|
| **Cannibalization gate** | Proposing a topic that competes with an existing post. Runs twice — at discovery and again before drafting. |
| **Inventory freshness check** | Drafting against a stale picture of the site. A snapshot over 7 days old hard-stops the run. |
| **The quality rubric** | Shipping a draft that fails SEO/structure standards. If it fails, the prose is fixed and re-checked — never waved through. |
| **`status=draft` only** | The pipeline publishing anything. A human is always the publish gate. |
| **Host lock** | Pushing content to the wrong website. Every WordPress call is rejected unless it targets the configured site. |
| **The heartbeat** | The pipeline failing silently. If the jobs stop firing (e.g. the VPS goes down), the cloud canary raises an alarm within 36 hours. |
| **State files** | Drafting the same topic twice. Each day's progress is tracked on disk. |

---

## 8. Where to go next

- **Setting it up?** → [DEPLOYMENT-SOP.md](DEPLOYMENT-SOP.md) — the exact
  step-by-step checklist.
- **Operating a live install?** → [SYSTEM-HANDOVER.md](SYSTEM-HANDOVER.md) —
  day-to-day operations and the failure-recovery playbook.
- **The rules the pipeline enforces in code** → [../CLAUDE.md](../CLAUDE.md).
- **Just opened the repo?** → [../ONBOARDING.md](../ONBOARDING.md).
