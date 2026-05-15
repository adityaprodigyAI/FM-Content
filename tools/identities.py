"""External-system IDs the content pipeline needs.

ALL values here are loaded from `client_config.toml` at the repo root. To
retarget the pipeline to a new client, edit `client_config.toml` — never this
file. See docs/DEPLOYMENT-SOP.md.

The constant names below are kept stable (some carry legacy First-Movers-
flavoured names like JOSH_MCCOY_WP_USER_ID) so that every importer across
tools/ keeps working. New generic aliases (WP_AUTHOR_ID, APPROVER_CLICKUP_USER_ID,
...) are provided alongside — prefer those in new code.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Final

# ---------------------------------------------------------------------------
# Load client_config.toml (the single per-client config file)
# ---------------------------------------------------------------------------

CLIENT_CONFIG_PATH: Final[Path] = (
    Path(__file__).resolve().parents[1] / "client_config.toml"
)


def _load_config() -> dict[str, Any]:
    if not CLIENT_CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"client_config.toml not found at {CLIENT_CONFIG_PATH}. "
            f"Copy it from the repo template and fill in the client's values. "
            f"See docs/DEPLOYMENT-SOP.md."
        )
    with CLIENT_CONFIG_PATH.open("rb") as fh:
        return tomllib.load(fh)


CLIENT_CONFIG: Final[dict[str, Any]] = _load_config()

_brand = CLIENT_CONFIG["brand"]
_wp = CLIENT_CONFIG["wordpress"]
_cu = CLIENT_CONFIG["clickup"]
_searchable = CLIENT_CONFIG.get("searchable", {})
_ga4 = CLIENT_CONFIG.get("ga4", {})
_gsc = CLIENT_CONFIG.get("gsc", {})
_discovery = CLIENT_CONFIG.get("discovery", {})
_schedule = CLIENT_CONFIG.get("schedule", {})

# ---------------------------------------------------------------------------
# Brand / site
# ---------------------------------------------------------------------------

BRAND_NAME: Final[str] = _brand["name"]
SITE_BASE_URL: Final[str] = _brand["site_base_url"].rstrip("/")
SITE_HOST: Final[str] = _brand["site_host"]

# ---------------------------------------------------------------------------
# WordPress
# ---------------------------------------------------------------------------

WP_AUTHOR_ID: Final[int] = int(_wp["author_id"])
# Legacy alias — kept so existing importers keep working.
JOSH_MCCOY_WP_USER_ID: Final[int] = WP_AUTHOR_ID

VALID_WP_CATEGORY_IDS: Final[frozenset[int]] = frozenset(
    int(c) for c in _wp["category_ids"]
)

# Named category constants. These are positional aliases over the configured
# category id list — kept for the external_links.py importer. A new client's
# category ids simply map by position; if a client has fewer than 7 blog
# categories, the trailing aliases fall back to the last configured id.
_cat_list: Final[list[int]] = [int(c) for c in _wp["category_ids"]]


def _cat(index: int) -> int:
    return _cat_list[index] if index < len(_cat_list) else _cat_list[-1]


WP_CATEGORY_AGI: Final[int] = _cat(0)
WP_CATEGORY_AI_IN_BUSINESS: Final[int] = _cat(1)
WP_CATEGORY_AI_TOOLS: Final[int] = _cat(2)
WP_CATEGORY_AI_CONSULTING: Final[int] = _cat(3)
WP_CATEGORY_AI_AUTOMATION: Final[int] = _cat(4)
WP_CATEGORY_AI_SALES: Final[int] = _cat(5)
WP_CATEGORY_AI_MARKETING: Final[int] = _cat(6)

# ---------------------------------------------------------------------------
# ClickUp
# ---------------------------------------------------------------------------

FIRST_MOVERS_CLICKUP_WORKSPACE_ID: Final[str] = str(_cu["workspace_id"])
CLICKUP_WORKSPACE_ID: Final[str] = FIRST_MOVERS_CLICKUP_WORKSPACE_ID  # generic alias

CONTENT_PROJECTS_LIST_ID: Final[str] = str(_cu["content_projects_list_id"])
CONTENT_PIPELINE_LIST_ID: Final[str] = CONTENT_PROJECTS_LIST_ID

CONTENT_PIPELINE_STATUS_TASK_ID: Final[str] = str(_cu["pipeline_status_task_id"])
CONTENT_PIPELINE_STATUS_TASK_URL: Final[str] = (
    f"https://app.clickup.com/t/{CONTENT_PIPELINE_STATUS_TASK_ID}"
)

APPROVER_CLICKUP_USER_ID: Final[int] = int(_cu["approver_user_id"])
# Legacy alias.
NIKKI_CLICKUP_USER_ID: Final[int] = APPROVER_CLICKUP_USER_ID

# Display name of the approver — used only in human-readable ClickUp comments.
APPROVER_NAME: Final[str] = str(_cu.get("approver_name", "the approver"))

CTA_APPROVER_CLICKUP_USER_ID: Final[int | None] = (
    int(_cu["cta_approver_user_id"]) if _cu.get("cta_approver_user_id") else None
)
# Legacy alias.
JOSH_CLICKUP_USER_ID: Final[int | None] = CTA_APPROVER_CLICKUP_USER_ID

# Display name of the CTA approver — used only in ClickUp comment text.
CTA_APPROVER_NAME: Final[str] = str(_cu.get("cta_approver_name", "the CTA approver"))

# ---------------------------------------------------------------------------
# Searchable / GA4 / GSC
# ---------------------------------------------------------------------------

SEARCHABLE_PROJECT_ID: Final[str] = str(_searchable.get("project_id", ""))
GA4_PROPERTY_ID: Final[str] = str(_ga4.get("property_id", ""))
GSC_SITE_URL: Final[str] = str(_gsc.get("site_url", ""))

# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

# Monday..Sunday competitor rotation for the Ahrefs gap source.
GAP_DISCOVERY_COMPETITOR_ROTATION: Final[tuple[str, ...]] = tuple(
    _discovery.get("competitor_rotation", [])
)
# De-duplicated set — kept for the ahrefs_gap importer's legacy name.
GAP_DISCOVERY_COMPETITORS: Final[tuple[str, ...]] = tuple(
    dict.fromkeys(GAP_DISCOVERY_COMPETITOR_ROTATION)
)
KD_CEILING: Final[int] = int(_discovery.get("kd_ceiling", 60))


def competitor_for_weekday(weekday: int) -> str:
    """Return the rotation competitor for a weekday (0=Monday .. 6=Sunday)."""
    rotation = GAP_DISCOVERY_COMPETITOR_ROTATION
    if not rotation:
        raise ValueError("discovery.competitor_rotation is empty in client_config.toml")
    return rotation[weekday % len(rotation)]


# ---------------------------------------------------------------------------
# Audience routing
# ---------------------------------------------------------------------------

# audience -> CTA destination path (relative, as written in client_config.toml).
# The rubric validates a draft's CTA by substring-matching this path.
AUDIENCE_TO_CTA_PATH: Final[dict[str, str]] = {
    audience: str(path)
    for audience, path in CLIENT_CONFIG.get("audience_routing", {}).items()
}

# audience -> CTA destination URL (absolute). draft.py uses this for cta_url.
AUDIENCE_TO_CTA_URL: Final[dict[str, str]] = {
    audience: SITE_BASE_URL + path if path.startswith("/") else path
    for audience, path in AUDIENCE_TO_CTA_PATH.items()
}

# ---------------------------------------------------------------------------
# Schedule / timezones
# ---------------------------------------------------------------------------

# The timezone the operator's local machine (running /loop) is in. CronCreate
# interprets /loop cron expressions in THIS timezone, not UTC.
OPERATOR_TIMEZONE: Final[str] = str(
    _schedule.get("operator_timezone", "UTC")
)
# The timezone daily-idea uses to key its per-day state files.
CONTENT_TIMEZONE: Final[str] = str(
    _schedule.get("content_timezone", "UTC")
)
# /loop cron expressions, in operator-local time.
DAILY_IDEA_LOCAL_CRON: Final[str] = str(
    _schedule.get("daily_idea_local_cron", "")
)
POLLING_DRAFTER_LOCAL_CRON: Final[str] = str(
    _schedule.get("polling_drafter_local_cron", "")
)

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

GA4_PROPERTY_ID_ENV_VAR: Final[str] = "FM_GA4_PROPERTY_ID"
RUBRIC_SKILL_NAME: Final[str] = CLIENT_CONFIG.get("rubric", {}).get(
    "skill_name", "firstmovers-blog-rubric"
)
