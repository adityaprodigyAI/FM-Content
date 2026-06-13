# FM-Content — VPS Access Guide

> **For:** the FirstMovers.ai client/team taking over operation of the content-automation VPS.
> **Purpose:** everything you need to log into the server, verify the content pipeline is running, and operate it day-to-day.
> **Before you send this:** the operator (Aditya) must fill in every `<<FILL IN>>` placeholder. Those are secrets — share them through a password manager or an encrypted channel, **not** in plain email or chat.

---

## 1. What the VPS is

A small always-on Linux server (Hostinger KVM) that runs the FirstMovers.ai daily blog-draft pipeline 24/7. Three scheduled jobs run on it automatically; it produces one WordPress blog draft per day for review. You normally never touch it — you only log in when something needs checking or a credential needs refreshing.

| Property | Value |
|---|---|
| Provider | Hostinger (KVM VPS) |
| IP address | `187.77.146.79` |
| OS | Ubuntu 24.04 LTS |
| Login user | `fmcontent` |
| System timezone | America/Phoenix (fixed UTC-7, no DST) |
| Project directory | `/home/fmcontent/fm-content` |
| Logs directory | `/home/fmcontent/fm-content/logs` |

---

## 2. Accounts and credentials you need

Collect all of these before you start. The operator supplies the `<<FILL IN>>` items.

| # | What | Value / where to get it |
|---|---|---|
| 1 | **Hostinger account login** (to manage the VPS itself — reboot, console, billing) | Email: `<<FILL IN>>` · Password: `<<FILL IN — share via password manager>>` |
| 2 | **SSH login to the server** | User `fmcontent` @ `187.77.146.79`. Auth method: **SSH key** (recommended) or password — `<<FILL IN which one + the key file or password>>` |
| 3 | **SSH private key file** (if key-based) | `<<FILL IN — send the key file securely; never paste it in chat>>` |
| 4 | **`sudo` password** for the `fmcontent` user (for admin commands) | `<<FILL IN>>` |
| 5 | **Claude Code subscription login** the server runs under | Account: `<<FILL IN>>` — used by `claude` CLI; you only need this if the login expires and must be redone |
| 6 | **GitHub deploy key / repo access** (the jobs commit state back) | Repo: `<<FILL IN repo URL>>` |

> **Security note:** items 1–4 give full control of the server. Treat them like banking passwords. Store them in a shared password manager (1Password, Bitwarden, etc.), not in this file.

---

## 3. How to log in (SSH)

### On Windows

**Option A — Windows Terminal / PowerShell (built-in OpenSSH):**

```powershell
# If using an SSH key:
ssh -i C:\path\to\fmcontent_key fmcontent@187.77.146.79

# If using a password (you'll be prompted):
ssh fmcontent@187.77.146.79
```

**Option B — PuTTY (GUI client):** download from putty.org, then:
1. Host Name: `187.77.146.79`, Port: `22`, Connection type: SSH.
2. If using a key: Connection → SSH → Auth → Credentials → browse to the `.ppk` key file. (Convert the `.pem`/OpenSSH key to `.ppk` with PuTTYgen first.)
3. Click **Open**, log in as `fmcontent`.

### On macOS / Linux

```bash
# Key-based:
ssh -i ~/path/to/fmcontent_key fmcontent@187.77.146.79

# Password-based:
ssh fmcontent@187.77.146.79
```

The first time you connect you'll see a "host authenticity" prompt — type `yes` to accept.

### If SSH fails entirely

Use the **Hostinger Browser Terminal**: log into the Hostinger account (credential #1) → VPS → your server → **Browser terminal / Console**. This gives you a terminal even if SSH is misconfigured or the firewall is blocking you.

---

## 4. First things to check after logging in

Run these to confirm the pipeline is alive:

```bash
# 1. Are the scheduled jobs installed? (should list 3 cron jobs)
crontab -l

# 2. Is the cron service running? (should say "active")
systemctl is-active cron

# 3. Does Claude Code still authenticate? (should reply "hi")
claude -p "hi"

# 4. Move into the project
cd ~/fm-content

# 5. Look at the most recent job logs
tail -n 40 logs/daily-idea.log
tail -n 40 logs/polling-drafter.log
tail -n 40 logs/inventory-refresh.log
```

If `claude -p "hi"` returns a login error, the Claude subscription session expired — run `claude` and complete `/login` again (you'll need credential #5).

---

## 5. The three scheduled jobs (what's running and when)

All times are Phoenix (the server's system clock).

| Job | When it runs | What it does | Workflow file |
|---|---|---|---|
| **daily-idea** | Every day 07:00 | Finds one new blog topic, checks it against everything already published, posts it to ClickUp for approval | `workflows/content-daily-idea-loop.md` |
| **polling-drafter** | Every 3 hours | Detects approved topics, writes the 2,500–3,800 word draft, pushes it to WordPress as a draft | `workflows/content-poll-and-draft-loop.md` |
| **inventory-refresh** | Monday 05:00 | Rebuilds the list of already-published posts (keeps the duplicate-protection gate accurate) | `workflows/content-inventory-refresh.md` |

There is also a **heartbeat** that runs in the Claude cloud (not on the VPS) every 12 hours. If the VPS goes down, the heartbeat posts an alert on the ClickUp status task `86ah3ywyh`. That's your early-warning signal that something needs attention on the server.

---

## 6. Where everything lives on the server

```
/home/fmcontent/fm-content/          ← the project
├── workflows/                       ← the job instructions (SOPs)
├── tools/                           ← the Python code that does the work
├── scripts/run-job.sh               ← the wrapper cron calls each tick
├── logs/                            ← job logs (daily-idea.log, etc.)
├── data/runs/_daily/                ← one JSON state file per day
├── data/inventory/                  ← snapshot of already-published posts
├── .env                             ← SECRETS (WordPress password, GA4 path) — never share or commit
└── .venv/                           ← the Python environment
```

The two most useful folders for day-to-day checking are **`logs/`** (what each job did) and **`data/runs/_daily/`** (the state of today's topic).

---

## 7. Connected services (the pipeline reaches these from the VPS)

The server doesn't store most of these credentials — they ride on the Claude account login or local config. You don't normally manage them, but here's the map so you know what's wired up:

| Service | What it's used for | How it's connected |
|---|---|---|
| WordPress (firstmovers.ai) | Pushing the blog drafts | Direct REST; username + Application Password stored in `.env` |
| Ahrefs | Topic discovery + search-results research | Through the Claude account connector |
| ClickUp | Posting topics for approval, reading approvals | Through the Claude account connector |
| Searchable | AI-search visibility gaps | Through the Claude account connector |
| Google Search Console | Striking-distance keyword discovery | Local `mcp-gsc` server; OAuth token at `~/.config/mcp-gsc/token.json` |
| Google Analytics 4 | Traffic-decay detection | Google service-account JSON (path in `.env`) |

---

## 8. Common operator tasks

**Watch a job run live (or see its last run):**
```bash
cd ~/fm-content
tail -f logs/daily-idea.log        # Ctrl+C to stop watching
```

**Manually trigger the inventory refresh (if a log shows a "stale inventory" error):**
```bash
cd ~/fm-content
source .venv/bin/activate
python -m tools.inventory_refresh
```

**Reboot the server (jobs resume automatically — cron survives reboots):**
- From Hostinger panel: VPS → your server → **Restart**, or
- From SSH: `sudo reboot` (you'll be disconnected; reconnect after ~30–60s)

**Re-login Claude Code if the subscription session expired:**
```bash
claude          # then follow the /login prompt
```

---

## 9. Troubleshooting quick reference

| Symptom | What to do |
|---|---|
| No new blog topic appeared in ClickUp today | SSH in → `tail -n 50 logs/daily-idea.log`. Check that `crontab -l` still lists the job and `systemctl is-active cron` says "active". |
| Approved topic never turned into a draft | `tail -n 50 logs/polling-drafter.log`. Confirm the ClickUp task was actually marked done/approved. |
| Got a "Heartbeat ALERT" on the ClickUp status task | The VPS may be down. Log into Hostinger, confirm the VPS is running (reboot if needed), then SSH in and run the §4 checks. |
| `claude -p "hi"` returns a login/auth error | Run `claude` and redo `/login`. |
| A job log shows `StaleInventoryError` | Run the inventory refresh (see §8). |
| WordPress draft push was blocked (403 / firewall) | Drafts queue automatically and can be pushed from outside the firewall — escalate to the operator; this needs the GitHub fallback workflow. |
| SSH won't connect at all | Use the Hostinger **Browser Terminal** (§3) to get in and diagnose. |

---

## 10. Who to contact

| Role | Contact |
|---|---|
| Pipeline operator (built & maintains the system) | `<<FILL IN — Aditya's contact>>` |
| Hostinger support (server/billing issues) | hpanel.hostinger.com → Help, or 24/7 chat |

---

## 11. Reference docs (already in the repo)

For deeper detail than this access guide:

- `docs/SYSTEM-HANDOVER.md` — full plain-language explanation of how the pipeline works.
- `docs/DEPLOYMENT-SOP.md` — how the VPS was set up (and how to stand up a new one).
- `docs/HOW-IT-WORKS.md` — system overview.
- `CLAUDE.md` (repo root) — the operating rules the pipeline enforces.

---

> **Reminder:** delete or redact this file's `<<FILL IN>>` lines only after moving those secrets into a password manager. Never commit a copy of this file that contains real passwords or keys.
