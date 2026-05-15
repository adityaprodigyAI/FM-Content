---
name: fm-searchable
description: Use when querying Searchable.ai for AEO (Answer Engine Optimization) visibility data — which AI search queries firstmovers.ai shows up for, which topics we're cited on, share-of-voice vs competitors. Covers visibility endpoints and how to feed into tools/discover/searchable_aeo.py.
verified: 2026-05-12
---

# Searchable in FM-Content

Searchable.ai tracks brand visibility in **AI search engines** — ChatGPT, Perplexity, Claude, Gemini. This is a different signal from Google SERP. Fourth discovery source: "topics we're being cited on that we don't have content for yet."

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

- **SEO** (GSC, Ahrefs): "people Google'd this query and saw our site." Volume + position.
- **AEO** (Searchable): "an AI assistant answered a question and cited (or didn't cite) our site." Mention + sentiment.

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
| Empty `visibility` array | Project not configured in Searchable for the firstmovers.ai domain |
| Different domain in response | Wrong project_id; check `mcp__claude_ai_searchable__list_projects` |

## See also

- `fm-gsc` and `fm-ahrefs` — the SEO counterparts that complete the discovery quartet
- `fm-cannibalization` — AEO candidates still go through the gate
