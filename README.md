# FM-Content — FirstMovers.ai daily blog pipeline

An automated content engine that produces one search-optimized WordPress blog
**draft** per day for Nikki to review and publish. Every topic is grounded in
real signals (Ahrefs competitor gap, GSC striking-distance, GA4 traffic decay,
Searchable AEO) and provably non-overlapping with existing FirstMovers content.

It runs unattended, 24/7, on an always-on VPS.

## The flow in one paragraph

Every day at 07:00 Phoenix, the **daily-idea** job pulls topic candidates from
four discovery sources, runs them through a strict cannibalization gate, picks
the single strongest surviving topic, and posts one task to ClickUp for Nikki to
approve. Whenever Nikki marks a task done, the **polling-drafter** job (every 3
hours) re-runs cannibalization (defense in depth), researches the live SERP,
generates a 2,500-3,500 word **text-only** draft against the
firstmovers-blog-rubric, validates it (hard-fails on any rule violation), and
pushes it to WordPress as `status=draft`. A weekly **inventory-refresh** job
keeps the published-content snapshot current. Nikki polishes, adds a featured
image, gets CTA sign-off, and publishes. If the WAF blocks the push, the draft
queues to `data/runs/_pending-push/` and a GitHub Action pushes it from a
non-cloud IP.

## How it runs

The three jobs run as **system cron on an always-on Hostinger VPS** — each cron
tick launches headless Claude Code (`claude -p`) against the job's workflow
file. There is no `/loop` and no laptop dependency. A `/schedule` cloud
heartbeat is the independent canary if the VPS itself goes down.

- Plain-language walkthrough → [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md)
- Deploy for a new client → [docs/DEPLOYMENT-SOP.md](docs/DEPLOYMENT-SOP.md)
- Day-to-day operations → [docs/SYSTEM-HANDOVER.md](docs/SYSTEM-HANDOVER.md)

## Quick start (local dev / verification)

```bash
pip install -e ".[ga4,dev]"
pytest -q                            # all tests pass before any production run
python -c "import tools.identities"  # config parses
python -m tools.inventory_refresh    # rebuild the inventory snapshot
```

## Hard rules (enforced in code, never bypass)

1. `status=draft` on creation. Nikki is the only publish gate.
2. Author = Josh McCoy (WordPress user 3).
3. No "free audit" anywhere — body, CTA, newsletter.
4. No em dashes anywhere (Josh April 2026 directive — hyphens only).
5. No trailing period in titles.
6. Audience routing: `done-for-you` → `/consulting/`; `diy` → `/labs/`. Never crossed.
7. Inventory snapshot must be ≤ 7 days old before any draft.
8. Cannibalization gate hard-blocks on slug, focus_keyword, or top organic
   keyword exact match — critical/high severity never reaches Nikki.
9. Discovery candidates must carry full provenance (`discovery_source`,
   `discovery_id`, `discovery_evidence`).
10. **v1 ships text-only drafts.** No images in the body. To re-enable image
    requirements, see `tools/rubric.py::MIN_IMAGE_COUNT` and the rubric
    SKILL.md section 6.

## Directory layout

```
client_config.toml          The single per-client config file
.env / .env.example         Secrets (gitignored) + template
tools/                      Deterministic Python modules
├── identities.py           Loads client_config.toml — the config↔code bridge
├── inventory.py            Loads + asserts freshness on the snapshot
├── inventory_refresh.py    Rebuilds the snapshot from MCPs
├── discover/               One extractor per discovery signal source
├── cannibalization.py      The strict overlap gate
├── daily.py                Per-day state machine (DailyState)
├── draft.py                Prose assembly + rubric validation
├── rubric.py               The hard-fail validators
├── push_wp.py              WP draft push (direct REST, browser UA)
├── push_archive.py         Path B GitHub Actions fallback for WAF blocks
├── ga4.py                  GA4 direct SDK wrapper
├── external_links.py       Curated citation allowlist per category
├── internal_links.py       Audience-routed internal-link picker
└── identities.py / schemas.py / rank_math.py / ...
data/
├── inventory/<host>.json   The published-content snapshot
└── runs/_daily/<date>.json Per-day pipeline state
workflows/                  Markdown SOPs the cron jobs execute
.claude/skills/             The process skills + the blog-rubric skill
.github/workflows/          Daily inventory check + WAF-fallback push
tests/                      pytest — 0 live network calls
```

## See also

- [CLAUDE.md](CLAUDE.md) — operating instructions (the flow, hard rules, MCP map)
- [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) — plain-language walkthrough
- [docs/DEPLOYMENT-SOP.md](docs/DEPLOYMENT-SOP.md) — onboard a new client onto a VPS
- [docs/SYSTEM-HANDOVER.md](docs/SYSTEM-HANDOVER.md) — day-to-day operations
- [ONBOARDING.md](ONBOARDING.md) — pick-your-path entry point
- [.claude/skills/firstmovers-blog-rubric/SKILL.md](.claude/skills/firstmovers-blog-rubric/SKILL.md) — what "good prose" looks like
