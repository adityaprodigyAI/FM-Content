---
name: fm-ahrefs
description: Use when calling any Ahrefs endpoint in the FM-Content pipeline — competitor gap discovery, SERP intent, keyword research, or per-post backlink/traffic snapshots. Covers MCP-vs-direct-REST routing, monetary unit convention (USD cents), competitor rotation, common pitfalls, and failure modes.
verified: 2026-05-12
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
| `/loop` in local Claude Code session (current production) | `mcp__ahrefs__*` MCP tools OR `tools.ahrefs.*` direct REST — both work. Prefer MCP for parity. |
| `/schedule` cloud routine (legacy, being phased out) | `mcp__ahrefs__*` MCP tools ONLY (the claude.ai Ahrefs connector, UUID `09f92d25-0521-43d1-8b8e-d3124f9073e4`). Direct REST is blocked by the sandbox proxy ("Host not in allowlist"). |
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
| Saturday | deloitte.com | tax + advisory |
| Sunday | mckinsey.com | freshest signal for week-ahead planning |

In a /loop daily run we layer **GSC striking-distance** and **GA4 decay** and **Searchable AEO** on top, so Ahrefs alone is no longer the sole signal. But it remains the seed for competitor-gap candidates.

## Common pitfalls

1. **`mode` matters.** `mode="subdomains"` for company-wide pulls, `mode="domain"` for a single domain. Pulling McKinsey with `mode="domain"` will miss `www.mckinsey.com` vs root.
2. **`date` is required for v3 endpoints.** Pass today's date in `YYYY-MM-DD`.
3. **`limit=100` is the sweet spot.** 1000+ explodes payload size and the cannibalization gate runtime.
4. **`order_by="sum_traffic:desc"`** — sort by traffic, NOT by keyword volume. Traffic accounts for the competitor's actual rank.
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

## See also

- `fm-cannibalization` — the gate that filters Ahrefs candidates before they reach the slate
- `fm-prose-generation` — uses `serp-overview` to read top-10 results before drafting
- `firstmovers-blog-rubric` — canonical published-post profile
