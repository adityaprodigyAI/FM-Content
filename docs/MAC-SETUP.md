# FM-Content — New Mac Setup Runbook

> Migrating the project to a new Mac for development + operations. This repo clone
> gives you all the code, config, and pipeline state. Three secrets live **outside**
> git and must be copied securely (see §3). The production VPS keeps running on its
> own — the Mac is your dev/control station, **not** a redeploy.

---

## 0. What travels in the repo vs what you copy by hand

| Comes with the clone (already committed) | Copy securely, by hand (NOT in git) |
|---|---|
| All source: `tools/`, `workflows/`, `tests/`, `scripts/` | `.env` (WordPress app password, GA4 path) |
| `client_config.toml` (IDs/config — no secrets) | GA4 service-account JSON (lives outside the repo) |
| `data/inventory/` + `data/runs/` (pipeline state) | VPS SSH key `~/.ssh/fm_content_vps` (+ `.pub`) |
| All docs (`docs/`, `CLAUDE.md`, `README.md`, this file) | |
| `pyproject.toml`, `.env.example` | |

The `claude-seo/` skill is **not** committed (it's a separate vendored repo) — reinstall it on the Mac in §2.5.

---

## 1. Prerequisites

```bash
# Homebrew (if not installed): https://brew.sh
brew install python@3.13 node git
```

## 2. Clone + Python environment

```bash
git clone https://github.com/adityaprodigyAI/FM-Content.git ~/fm-content
cd ~/fm-content
git config core.autocrlf input            # normalise line endings (Windows -> macOS)

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[ga4,dev]"
pytest -q                                  # all tests should pass
```

### 2.5 Claude Code + claude-seo skill

```bash
npm i -g @anthropic-ai/claude-code
claude                                     # run /login with the subscription account
claude -p "hi"                             # verify headless mode works

# Re-install the SEO skill (the ./claude-seo clone is NOT in this repo):
git clone https://github.com/AgriciDaniel/claude-seo.git
bash claude-seo/install.sh                 # installs ~/.claude/skills/seo + agents
# restart Claude Code, then verify:  /seo
```

Logging into `claude` reconnects the account-level MCP connectors automatically:
**Ahrefs, ClickUp, Searchable, and FirstMoversWP** — no files to copy.

### 2.6 Local mcp-gsc (Google Search Console)

```bash
git clone <mcp-gsc repo> ~/mcp-gsc && cd ~/mcp-gsc
python3 -m venv .venv && source .venv/bin/activate && pip install -e .
# Then EITHER copy the laptop's token  OR  re-run the OAuth flow:
mkdir -p ~/.config/mcp-gsc
#   copy ~/.config/mcp-gsc/token.json from the old laptop  (has a refresh token)
# Register mcp-gsc in Claude Code's MCP settings.
```

---

## 3. Copy the three out-of-git secrets (securely)

Move these via a password manager / AirDrop / encrypted transfer — never plain email/chat.

### 3.1 `.env`
Copy the laptop's `.env` to the repo root, then **edit one line** — the GA4 path is a
Windows path and must point to the Mac location from §3.2:

```
GOOGLE_APPLICATION_CREDENTIALS=/Users/<you>/.config/fm-content/ga4-sa.json
```

### 3.2 GA4 service-account JSON  ⚠️ keep it OUTSIDE the repo
On Windows it lives on the Desktop. Its current filename (`client_secret_…json`) does
**not** match `.gitignore`, so do **not** drop it in the repo under that name or it could
get committed. Put it outside the repo:

```bash
mkdir -p ~/.config/fm-content
cp /path/from/transfer/client_secret_*.json ~/.config/fm-content/ga4-sa.json
chmod 600 ~/.config/fm-content/ga4-sa.json
```
(Alternatively keep it in the repo only if renamed to `*-service-account.json`, which IS gitignored.)

### 3.3 VPS SSH key
```bash
cp /path/from/transfer/fm_content_vps     ~/.ssh/fm_content_vps
cp /path/from/transfer/fm_content_vps.pub ~/.ssh/fm_content_vps.pub
chmod 600 ~/.ssh/fm_content_vps

cat >> ~/.ssh/config <<'EOF'
Host fmcontent
  HostName 187.77.146.79
  User fmcontent
  IdentityFile ~/.ssh/fm_content_vps
  StrictHostKeyChecking accept-new
EOF

ssh fmcontent           # should log into the VPS
```

Full VPS operating guide: `docs/CLIENT-VPS-ACCESS.md`.

---

## 4. Verify end-to-end

```bash
cd ~/fm-content && source .venv/bin/activate
python -c "import tools.identities; print('config OK')"
pytest -q
python -m tools.inventory_refresh         # rebuilds the published-content snapshot
ssh fmcontent 'crontab -l && systemctl is-active cron'   # VPS jobs alive
claude -p "hi"                            # connectors reachable
# In Claude Code:  /seo   (skill available)
```

---

## 5. Notes / gotchas

- **VPS is untouched.** Migrating the laptop changes nothing on the server; its cron jobs keep running. Don't redeploy it.
- Ignore the `.ps1` installers in `claude-seo/` on macOS — use the `.sh` versions.
- The project `.claude/settings.local.json` is gitignored (machine-specific). Any Windows-only permission entries simply won't carry over — that's fine.
- claude.ai connectors are account-level: once `claude /login` is done, Ahrefs/ClickUp/Searchable/WordPress work without copying anything.
- Reference docs already in the repo: `README.md`, `ONBOARDING.md`, `docs/DEPLOYMENT-SOP.md`, `docs/SYSTEM-HANDOVER.md`, `docs/CLIENT-GOOGLE-CREDENTIALS-SOP.md`, `CLAUDE.md`.
