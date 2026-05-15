---
name: fm-ga4
description: Use when querying Google Analytics 4 to detect traffic decay on published posts (which posts need refresh vs which need replacement). Covers the analytics-mcp-hangs workaround via tools/ga4.py, the decay-detection query, and how to feed into tools/discover/ga4_gap.py.
verified: 2026-05-12
---

# Google Analytics 4 in FM-Content

GA4 is how we detect **traffic decay** — pages that used to rank, slipped, and need either a refresh or a replacement post. Third discovery source (after Ahrefs gap and GSC striking-distance) and the one that surfaces "fix what's broken" candidates rather than "find net-new" ones.

## Critical constraint — use the direct SDK, not the MCP

`mcp__analytics-mcp__*` hangs on most queries (observed 2026-04 and again 2026-05). DO NOT rely on it.

Use `tools/ga4.py` which wraps `google-analytics-data` SDK directly. Same auth (GA4 service account JSON), no MCP middleman.

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
| "Did this post lose its rank or its CTR?" | GSC `get_search_by_page_query` then compare to GA4 sessions |
| "Is the site overall up or down quarter-over-quarter?" | GA4 |

GSC tells you about impressions and rank. GA4 tells you about sessions. Decay shows up in GA4 first because GSC rank changes propagate to GA4 sessions with ~7-day lag.

## Auth

Service account JSON at the path `tools/ga4.py` expects (env var `GOOGLE_APPLICATION_CREDENTIALS` or its own config). Service account needs "Viewer" role on the GA4 property.

## Failure modes

| Symptom | Diagnosis |
|---|---|
| `PERMISSION_DENIED` | Service account not added to GA4 property OR wrong property ID |
| All rows have 0 sessions | Date range too narrow OR property has no data (check in GA4 UI) |
| `run_report` hangs > 30s | DO NOT retry into the MCP. Use the SDK directly via `tools.ga4`. |

## See also

- `fm-gsc` — pair with GA4 for rank-vs-session diagnosis
- `fm-cannibalization` — decay candidates still go through the gate (the post that's decaying may be the post we'd accidentally cannibalize)
