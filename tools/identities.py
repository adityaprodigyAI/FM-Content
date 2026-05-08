"""External-system IDs the content pipeline needs.

Hardcoded once so we don't have to look them up on every run. Values that
aren't yet known are set to None and the pipeline will fail loudly when it
needs them, which is intentional — better than silently using the wrong ID.

Verified 2026-04-27 against `mcp__first-movers-wordpress__*` and
`mcp__claude_ai_ClickUp__*`. Ported from firstmover-hub on 2026-05-08.
"""

from __future__ import annotations

from typing import Final

# WordPress (firstmovers.ai) — resolved via wp_users_search on 2026-04-17
JOSH_MCCOY_WP_USER_ID: Final[int] = 3  # slug: websitegenius

# Blog category IDs — per CLAUDE.md "Blog Categories (WordPress)" section
WP_CATEGORY_AI_CONSULTING: Final[int] = 27
WP_CATEGORY_AI_AUTOMATION: Final[int] = 28
WP_CATEGORY_AI_SALES: Final[int] = 29
WP_CATEGORY_AI_MARKETING: Final[int] = 30
WP_CATEGORY_AI_IN_BUSINESS: Final[int] = 13
WP_CATEGORY_AI_TOOLS: Final[int] = 14
WP_CATEGORY_AGI: Final[int] = 10

VALID_WP_CATEGORY_IDS: Final[frozenset[int]] = frozenset(
    {
        WP_CATEGORY_AI_CONSULTING,
        WP_CATEGORY_AI_AUTOMATION,
        WP_CATEGORY_AI_SALES,
        WP_CATEGORY_AI_MARKETING,
        WP_CATEGORY_AI_IN_BUSINESS,
        WP_CATEGORY_AI_TOOLS,
        WP_CATEGORY_AGI,
    }
)

# ClickUp — verified 2026-04-27
FIRST_MOVERS_CLICKUP_WORKSPACE_ID: Final[str] = "9013404166"
CONTENT_OPERATIONS_SPACE_ID: Final[str] = "901313618313"
CONTENT_PROJECTS_LIST_ID: Final[str] = "901326229295"
KEYWORDS_SEO_LIST_ID: Final[str] = "901326229331"
RESEARCH_LIBRARY_LIST_ID: Final[str] = "901326229299"
CONTENT_PIPELINE_LIST_ID: Final[str] = CONTENT_PROJECTS_LIST_ID
CONTENT_PIPELINE_STATUS_TASK_ID: Final[str] = "86ah3ywyh"
CONTENT_PIPELINE_STATUS_TASK_URL: Final[str] = "https://app.clickup.com/t/86ah3ywyh"

# Team member ClickUp IDs (verified via clickup_get_workspace_members)
NIKKI_CLICKUP_USER_ID: Final[int] = 26221739     # blog publish gate
JOSH_CLICKUP_USER_ID: Final[int] = 120239313     # final approver
ARHAM_CLICKUP_USER_ID: Final[int] = 96728606     # pipeline architect
MILES_CLICKUP_USER_ID: Final[int] = 118031942    # PM
JAKE_CLICKUP_USER_ID: Final[int] = 112079589     # sales

# Searchable
SEARCHABLE_PROJECT_ID: Final[str] = "a04206b9-89ae-4175-8d4d-af48af32a1c6"

# Site
SITE_BASE_URL: Final[str] = "https://firstmovers.ai"
SITE_HOST: Final[str] = "firstmovers.ai"

# Competitors used by the Ahrefs gap discovery source. These are domains we
# expect to outrank on First Movers' core terms — keywords they rank for and
# we don't represent the largest content gap.
GAP_DISCOVERY_COMPETITORS: Final[tuple[str, ...]] = (
    "mckinsey.com",
    "accenture.com",
    "deloitte.com",
    "hubspot.com",
)

# GA4 property — set in .env or via secrets
GA4_PROPERTY_ID_ENV_VAR: Final[str] = "FM_GA4_PROPERTY_ID"
