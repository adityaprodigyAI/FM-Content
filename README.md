# FM-Content — FirstMovers.ai weekly blog pipeline

A weekly content engine that posts 7 WordPress blog drafts into Nikki's review queue every Wednesday. Drafts are grounded in real signals (GSC striking-distance, Ahrefs competitor gap, Searchable AEO, GA4 high-traffic) and provably non-overlapping with existing FirstMovers content.

## The flow in one paragraph

Sunday 07:00 Phoenix, the Sunday job rebuilds the published-content inventory (WordPress posts + pages + Rank Math focus keywords + Ahrefs organic keywords), pulls topic candidates from four discovery sources, runs them through a strict cannibalization gate, picks the top 12, and posts a parent task to ClickUp with 12 subtasks for Nikki to approve. Nikki ticks ≤7 by Tuesday EOD. Wednesday 09:00 Phoenix, the Wednesday job reads her approvals, re-runs cannibalization (defense in depth), generates 2,500–3,500 word **text-only** drafts using Ahrefs SERP intent + the firstmovers-blog-rubric, validates against the rubric (hard-fails on any rule violation), and pushes the drafts to WordPress as `status=draft`. Nikki adds a featured image (and any inline images, if she wants them) post-publish. If the Cloudways/Wordfence WAF blocks the MCP push, drafts are queued to `data/runs/_pending-push/` and pushed via a GitHub Actions workflow that runs from a non-cloud IP.

## Quick start

```bash
pip install -e ".[dev]"
pytest -q                         # all tests pass before any production run
python -m tools.inventory_refresh # rebuild snapshot from MCPs (run once weekly)
python -m tools.slate --week 2026-W22 --dry-run   # Sunday slate dry run
python -m tools.slate --week 2026-W22 --emit      # post to ClickUp
python -m tools.draft --week 2026-W22 --dry-run   # Wednesday draft dry run
python -m tools.draft --week 2026-W22 --push      # write drafts to WP
```

## Hard rules (enforced in code, never bypass)

1. `status=draft` on creation. Nikki is the only publish gate.
2. Author = Josh McCoy (WordPress user 3).
3. No "free audit" anywhere — body, CTA, newsletter.
4. No em dashes anywhere (Josh April 2026 directive — hyphens only).
5. Audience routing: `done-for-you` → `/consulting/`; `diy` → `/labs/`. Never crossed.
6. Inventory snapshot must be ≤ 7 days old before any draft.
7. Cannibalization gate hard-blocks on slug, focus_keyword, or top organic keyword exact match.
8. Discovery candidates must carry full provenance (`discovery_source`, `discovery_id`, `discovery_evidence`).
9. **v1 ships text-only drafts.** No images in the body. Nikki adds a featured image post-publish if she wants one. To re-enable image requirements, see `tools/rubric.py::MIN_IMAGE_COUNT` and the rubric SKILL.md section 6.

## Directory layout

```
tools/                       Deterministic Python modules
├── identities.py            WP user, category IDs, ClickUp IDs, site URL
├── inventory.py             Loads + asserts freshness on the snapshot
├── inventory_refresh.py     CLI that rebuilds the snapshot from MCPs
├── discover/                One extractor per signal source
├── cannibalization.py       Strict 4-rule gate
├── slate.py                 Sunday job — picks top 12, posts to ClickUp
├── clickup.py               ClickUp emit + read approvals
├── draft.py                 Wednesday job — generates prose, validates, pushes
├── rubric.py                The hard-fail validators from the rubric skill
├── schemas.py               FAQPage JSON-LD builder
├── external_links.py        Curated citation allowlist per category
├── internal_links.py        Tier-1 + sibling-blog selector, audience-biased
├── push_wp.py               MCP push first; GH Actions fallback on WAF block
├── rank_math.py             Set focus_keyword + seo_title via Devora plugin
└── images.py                Pexels search + hotlinked references
data/
├── inventory/firstmovers-ai.json    Weekly snapshot (gitignored if large)
└── runs/
    ├── _title-slates/2026-WNN.json  Sunday output
    ├── _drafts/2026-WNN.json        Wednesday output
    └── _pending-push/               WAF fallback queue
workflows/                   Markdown SOPs (W80 layer 1)
.claude/skills/firstmovers-blog-rubric/SKILL.md   Writing rubric
.github/workflows/           Daily inventory check + WAF-fallback push
tests/                       pytest — 0 live network calls
```

## See also

- `CLAUDE.md` — operating instructions for Claude (MCP map, hard rules, the flow)
- `workflows/content-sunday-slate.md` — Sunday job agent contract
- `workflows/content-wednesday-draft.md` — Wednesday job agent contract
- `workflows/content-title-approval.md` — Nikki-facing SOP
- `.claude/skills/firstmovers-blog-rubric/SKILL.md` — what "good prose" looks like
