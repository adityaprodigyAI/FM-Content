---
name: fm-cannibalization
description: Use before proposing any new blog topic or right before assembling a draft. Captures the cannibalization gate semantics (the v5 bug that motivated rebuilding the pipeline), severity ladder, evidence fields, defense-in-depth re-check at draft time, and StaleInventoryError handling.
verified: 2026-05-12
---

# Cannibalization gate

The single most load-bearing rule in FM-Content: **never propose a topic that overlaps a topic firstmovers.ai has already published.** That was the v5 bug; this gate is the structural defense.

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

In `tools/slate.py` and `tools/daily.py`, anything `critical` or `high` is filtered out before reaching the top-N candidate selection. In `tools/draft.py::prepare_brief`, the gate runs AGAIN as defense-in-depth — if inventory changed between slate emission and draft generation, a topic that was clear can become a `critical` overlap.

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

The gate is deterministic given the same `(ProposedTopic, Inventory)` input. Re-running it produces the same severity. The draft-time re-check is cheap insurance, not a correctness fix.

## Failure modes

| Symptom | Cause |
|---|---|
| Gate returns `critical` on a topic that's clearly novel | Inventory has a stub post with the same focus keyword. Audit `data/inventory/firstmovers-ai.json` for that entry; may be a v4 ghost. |
| Gate returns `none` on an obvious dup | Inventory entry has `focus_keyword == None`. Refresh inventory; the gate refuses to run on degraded entries via `assert_complete()`. |
| `StaleInventoryError` even after refresh | Check `data/inventory/firstmovers-ai.json` mtime. If clock skewed, fix system time. |

## See also

- `firstmovers-blog-rubric` — what a clean post looks like once it clears the gate
- `fm-ahrefs`, `fm-gsc`, `fm-ga4`, `fm-searchable` — all discovery sources are gated through this
