---
name: fm-gsc
description: Use when calling Google Search Console MCP for striking-distance discovery, per-page query diagnosis, or inventory join. Covers position-band semantics, OAuth refresh, the /loop-only constraint (no claude.ai connector exists for GSC), and how to feed signals into tools/discover/gsc.py.
verified: 2026-05-12
---

# Google Search Console in FM-Content

GSC is the highest-conviction discovery signal we have because it's first-party — these are queries the firstmovers.ai site is **already showing up for**, not hypothetical opportunities. The job is to find the queries where one good push moves us from page 2 to page 1.

## Critical constraint — /loop only

As of 2026-05-09 there is no claude.ai built-in MCP connector for GSC. The `mcp__gsc__*` tools only exist in the local MCP environment (operator's workstation; future VM). Therefore:

- `/schedule` routines CANNOT use GSC. Don't try.
- `/loop`s in the operator's local Claude Code session CAN use it.
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

The workhorse for daily-idea discovery:

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
| 30+ | Ignore for discovery. |

## OAuth refresh

GSC uses Google OAuth. Tokens live where the `mcp__gsc__*` server expects them (typically `~/.config/gsc-mcp/token.json` on Linux; equivalent path on Windows — check the server's docs).

If you see `401 invalid_grant`, the refresh token has expired (Google revokes after 6 months of inactivity OR if the user revokes app access). Fix:

1. Run `mcp__gsc__reauthenticate` in a Claude session
2. Follow the device-code flow
3. New token persisted to disk; subsequent calls succeed

## Failure modes

| Symptom | Diagnosis |
|---|---|
| Empty rows even though site has traffic | `data_state="final"` excludes last 2-3 days. Try `data_state="all"` |
| `403 Forbidden` | Service account / user lacks "Restricted" permission on the GSC property |
| `429` | Per-property quota — back off and retry in 60s |
| `mcp__gsc__list_properties` returns empty | Wrong OAuth scope or wrong Google account |

## See also

- `fm-ga4` — pair with GSC to distinguish rank loss (GSC) from session loss (GA4)
- `fm-cannibalization` — striking-distance candidates still go through the gate
- `firstmovers-blog-rubric` — once a candidate clears, this is the target
