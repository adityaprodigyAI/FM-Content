"""clickup — emit slate task + read subtask approvals.

Two concerns in this module:

1. **Payload builders + parsers** (used by both weekly-mode AND cron-mode):
   The agent makes MCP calls; this module produces the payloads
   and parses the responses. Pure data transforms, easy to test.

2. **Direct REST wrappers** (LOCAL DEVELOPMENT ONLY):
   `create_task`, `get_task`, `create_task_comment`, `add_tag_to_task`.
   These hit `api.clickup.com` directly via urllib + a `CLICKUP_API_TOKEN`
   bearer header. Mirrors the SDK-bypass pattern in `tools/ahrefs.py`.

   **WARNING**: Do NOT use these direct-REST wrappers from a `/schedule`
   cloud routine. The routine sandbox proxy blocks outbound HTTP to
   `api.clickup.com` and returns `403 "Host not in allowlist"`. Cloud
   routines must use the ClickUp MCP connector (`clickup_create_task`,
   `clickup_get_task`, `clickup_create_task_comment`) which routes through
   claude.ai's authenticated connector infrastructure and bypasses the
   sandbox restriction. See `workflows/schedule-registration.md` for the
   full constraint description.

   The direct REST is useful for: local Claude Code sessions, ad-hoc
   diagnostics (`python -m tools.clickup check`), unit-test fixtures,
   one-off scripts run from a developer machine with unrestricted outbound.

Approval mechanism: parent task with one subtask per slate proposal.
A subtask with `status_type == "done"` (i.e., status name like "complete",
"closed", "published") is considered approved.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Final  # noqa: F401  — Final used in module-level constants
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .identities import (
    CONTENT_PIPELINE_STATUS_TASK_ID,
    CONTENT_PROJECTS_LIST_ID,
    NIKKI_CLICKUP_USER_ID,
)
from .slate import Slate, SlateProposal

CLICKUP_API_BASE: Final[str] = "https://api.clickup.com/api/v2"
CLICKUP_API_TOKEN_ENV: Final[str] = "CLICKUP_API_TOKEN"
DEFAULT_TIMEOUT_SECONDS: Final[int] = 30


# ClickUp API call shapes Claude will make. Recorded here so the Sunday
# agent has a single reference and the test suite can assert payload
# correctness without hitting the network.

DONE_STATUS_TYPES: Final[frozenset[str]] = frozenset({"done", "closed"})

# When ClickUp returns subtasks via clickup_get_task(subtasks=true), the
# `status` field is a bare string (the status name), not the rich object
# with a `.type` field. We need a name allowlist that maps to "done" semantics.
# These cover the canonical names across the FirstMovers ClickUp lists.
DONE_STATUS_NAMES: Final[frozenset[str]] = frozenset(
    {"published", "complete", "closed", "done", "ready"}
)


# ---------------------------------------------------------------------------
# Emit (Sunday)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParentTaskPayload:
    list_id: str
    name: str
    description: str
    assignees: list[int]


@dataclass(frozen=True)
class SubtaskPayload:
    parent_task_id: str
    name: str
    description: str
    assignees: list[int]
    custom_id: str  # focus_keyword, used to map approvals back to proposals


def build_parent_task_payload(slate: Slate) -> ParentTaskPayload:
    """Build the ClickUp parent-task payload for the slate.

    The agent calls:
      mcp__claude_ai_ClickUp__clickup_create_task(
          list_id=payload.list_id,
          name=payload.name,
          description=payload.description,
          assignees=payload.assignees,
      )
    """
    return ParentTaskPayload(
        list_id=CONTENT_PROJECTS_LIST_ID,
        name=f"Approve {slate.week} blog titles by Tue EOD",
        description=_render_slate_description(slate),
        assignees=[NIKKI_CLICKUP_USER_ID],
    )


def build_subtask_payloads(
    slate: Slate,
    *,
    parent_task_id: str,
) -> list[SubtaskPayload]:
    """One subtask per proposal."""
    out: list[SubtaskPayload] = []
    for prop in slate.proposals:
        out.append(
            SubtaskPayload(
                parent_task_id=parent_task_id,
                name=prop.working_title,
                description=_render_proposal_description(prop),
                assignees=[NIKKI_CLICKUP_USER_ID],
                custom_id=prop.focus_keyword,
            )
        )
    return out


def build_status_comment(slate: Slate, parent_task_id: str) -> str:
    """A short comment to post on the Pipeline Status task on emit."""
    by_source = ", ".join(
        f"{src}={n}" for src, n in slate.discovery_summary.get("by_source", {}).items()
    )
    return (
        f"Slate {slate.week} posted: {len(slate.proposals)} proposals "
        f"({by_source}). Parent task: https://app.clickup.com/t/{parent_task_id}"
    )


# ---------------------------------------------------------------------------
# Read approvals (Wednesday)
# ---------------------------------------------------------------------------


def parse_approved_subtasks(parent_task_response: Any) -> list[str]:
    """Return the list of focus_keywords whose subtasks are 'done'.

    Tolerates the wrapped MCP shape and a few common dict keys.

    Approval semantics:
      - subtask `status.type == "done"` OR `status.type == "closed"` -> approved
      - everything else                                              -> pending
    """
    payload = _unwrap(parent_task_response)
    if not isinstance(payload, dict):
        return []
    subtasks = payload.get("subtasks") or payload.get("children") or []
    if not isinstance(subtasks, list):
        return []

    approved: list[str] = []
    for st in subtasks:
        if not isinstance(st, dict):
            continue
        if not _is_subtask_done(st.get("status")):
            continue
        # Map back to focus_keyword. The Sunday job stored focus_keyword as
        # the subtask `custom_id` field; if missing, fall back to the
        # subtask name and let the caller resolve.
        custom_id = st.get("custom_id") or ""
        if isinstance(custom_id, str) and custom_id.strip():
            approved.append(custom_id.strip().lower())
            continue
        name = st.get("name") or ""
        if isinstance(name, str) and name.strip():
            approved.append(name.strip())
    return approved


def _is_subtask_done(status: Any) -> bool:
    """Recognize a 'done' subtask in two ClickUp response shapes:

    1. Rich object: {"id": "...", "status": "published", "type": "closed", ...}
       — used by clickup_get_task at task-detail level. The `.type` field is
       authoritative when present.
    2. Bare string: "published"
       — used by clickup_get_task(subtasks=true). Falls back to a name
       allowlist (DONE_STATUS_NAMES) since the type isn't surfaced.
    """
    if isinstance(status, dict):
        type_str = str(status.get("type") or "").strip().lower()
        if type_str:
            # The type field is authoritative when present
            return type_str in DONE_STATUS_TYPES
        # Type missing — fall back to status name
        name_str = str(status.get("status") or "").strip().lower()
        return name_str in DONE_STATUS_NAMES
    if isinstance(status, str):
        return status.strip().lower() in DONE_STATUS_NAMES
    return False


def filter_proposals_by_approval(
    slate: Slate,
    approved: list[str],
    *,
    max_approvals: int = 7,
) -> list[SlateProposal]:
    """Return the proposals whose focus_keyword (or working_title) is in `approved`."""
    norm = {a.strip().lower() for a in approved}
    out: list[SlateProposal] = []
    for prop in slate.proposals:
        if prop.focus_keyword.lower() in norm:
            out.append(prop)
            continue
        if prop.working_title.strip().lower() in norm:
            out.append(prop)
            continue
    return out[:max_approvals]


# ---------------------------------------------------------------------------
# Reply with edit URLs (after Wednesday push)
# ---------------------------------------------------------------------------


def build_edit_url_reply(
    week: str,
    edit_urls_by_focus_kw: dict[str, str],
    *,
    rank_math_set_count: int,
) -> str:
    """The Wednesday-job comment that goes back on the slate parent task."""
    lines = [
        f"Drafts pushed for {week}. {len(edit_urls_by_focus_kw)} of approved titles "
        f"now in WordPress as `status=draft`.",
        "",
    ]
    for focus_kw, url in sorted(edit_urls_by_focus_kw.items()):
        lines.append(f"- **{focus_kw}** -> {url}")
    lines.append("")
    lines.append(
        f"Rank Math meta set on {rank_math_set_count} of "
        f"{len(edit_urls_by_focus_kw)} drafts."
    )
    lines.append("Nikki: review, add featured image, request Josh CTA approval, publish.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internals — descriptions
# ---------------------------------------------------------------------------


def _render_slate_description(slate: Slate) -> str:
    head = (
        f"# {slate.week} blog title slate\n\n"
        f"Tick the subtasks of titles you want drafted. The Wednesday job "
        f"reads approvals and pushes the prose to WordPress as drafts.\n\n"
        f"**Approve at most 7 titles by Tuesday EOD Phoenix.**\n\n"
    )
    by_src = slate.discovery_summary.get("by_source", {})
    src_line = ", ".join(f"{k}={v}" for k, v in by_src.items())
    return head + f"Sources: {src_line}\n"


def _render_proposal_description(prop: SlateProposal) -> str:
    out = [
        f"**Focus keyword:** {prop.focus_keyword}",
        f"**Audience:** {prop.audience}",
        f"**Category:** {prop.category_id}",
        f"**Intent:** {prop.intent}",
        f"**Target publish date:** {prop.target_date}",
        "",
        f"**Angle:** {prop.one_line_angle}",
        "",
        "**Outline:**",
    ]
    for bullet in prop.outline_bullets:
        out.append(f"- {bullet}")
    out.extend([
        "",
        f"**Why this topic:** {prop.discovery_source} | "
        f"{prop.cannibalization_rationale}",
        "",
        "<!-- discovery_evidence: " + json.dumps(prop.discovery_evidence) + " -->",
    ])
    return "\n".join(out)


def _unwrap(response: Any) -> Any:
    """Strip the wrapped MCP `[{type:'text', text:'<json>'}]` shape if present."""
    if isinstance(response, list) and response and isinstance(response[0], dict) and response[0].get("type") == "text":
        try:
            return json.loads(response[0].get("text", "null"))
        except (json.JSONDecodeError, TypeError):
            return None
    return response


# ---------------------------------------------------------------------------
# Direct REST wrappers (cron/routine mode)
#
# Used by /schedule remote agents where the claude.ai ClickUp connector is
# unavailable. Mirrors the urllib-only pattern from tools/ahrefs.py.
#
# Auth: ClickUp uses the raw personal token as the Authorization header
# value (no "Bearer " prefix). Token starts with `pk_`.
#   Authorization: pk_96728606_XXX...
# ---------------------------------------------------------------------------


def create_task(
    list_id: str,
    *,
    name: str,
    markdown_description: str | None = None,
    description: str | None = None,
    assignees: list[int] | None = None,
    due_date: str | int | None = None,
    tags: list[str] | None = None,
    api_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Create a task in `list_id`. Returns raw ClickUp API response (dict with `id`).

    `due_date` accepts YYYY-MM-DD (interpreted as end-of-day UTC) or an int
    epoch-ms. Pass `markdown_description` for rich text; otherwise use plain
    `description`.
    """
    body: dict[str, Any] = {"name": name}
    if markdown_description is not None:
        body["markdown_description"] = markdown_description
    if description is not None:
        body["description"] = description
    if assignees:
        body["assignees"] = list(assignees)
    if tags:
        body["tags"] = list(tags)
    if due_date is not None:
        body["due_date"] = _to_epoch_ms(due_date)
        body["due_date_time"] = True
    return _request(
        method="POST",
        path=f"/list/{list_id}/task",
        body=body,
        api_token=api_token,
        timeout=timeout,
    )


def get_task(
    task_id: str,
    *,
    include_subtasks: bool = False,
    api_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Fetch a task with `status`, `assignees`, and optionally `subtasks`."""
    params: dict[str, Any] = {}
    if include_subtasks:
        params["include_subtasks"] = "true"
    return _request(
        method="GET",
        path=f"/task/{task_id}",
        params=params,
        api_token=api_token,
        timeout=timeout,
    )


def create_task_comment(
    task_id: str,
    *,
    comment_text: str,
    notify_all: bool = False,
    api_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Post a comment on a task. Returns `{id, hist_id, date}` on success."""
    return _request(
        method="POST",
        path=f"/task/{task_id}/comment",
        body={"comment_text": comment_text, "notify_all": notify_all},
        api_token=api_token,
        timeout=timeout,
    )


def add_tag_to_task(
    task_id: str,
    tag_name: str,
    *,
    api_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Add an existing tag to a task. Returns `{}` on success."""
    return _request(
        method="POST",
        path=f"/task/{task_id}/tag/{tag_name}",
        api_token=api_token,
        timeout=timeout,
    )


def _get_token(api_token: str | None) -> str:
    if api_token:
        return api_token
    token = os.environ.get(CLICKUP_API_TOKEN_ENV)
    if not token:
        raise RuntimeError(
            f"ClickUp API token not set. Pass api_token=, or set "
            f"${CLICKUP_API_TOKEN_ENV}. Generate one at "
            f"https://app.clickup.com/settings/apps (Personal token, starts with 'pk_')."
        )
    return token


def _to_epoch_ms(value: str | int | date | datetime) -> int:
    """Coerce a date-ish value to epoch-ms (UTC). 23:59:59 if just a date."""
    if isinstance(value, int):
        return value
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(value, date):
        dt = datetime(value.year, value.month, value.day, 23, 59, 59, tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)
    if isinstance(value, str):
        try:
            d = datetime.strptime(value, "%Y-%m-%d").replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc,
            )
            return int(d.timestamp() * 1000)
        except ValueError as e:
            raise ValueError(f"due_date string must be YYYY-MM-DD, got {value!r}") from e
    raise TypeError(f"due_date must be str|int|date|datetime, got {type(value).__name__}")


def _request(
    *,
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    api_token: str | None,
    timeout: int,
) -> dict[str, Any]:
    token = _get_token(api_token)
    url = CLICKUP_API_BASE + path
    if params:
        url += "?" + urlencode(params)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {
        "Authorization": token,
        "Accept": "application/json",
        "User-Agent": "fm-content/0.1 (+clickup-bypass)",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — known host
            text = resp.read().decode("utf-8")
            if not text.strip():
                return {}
            return json.loads(text)
    except HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="ignore")[:500]
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(
            f"ClickUp API HTTP {e.code} {e.reason} ({method} {path}): {err_body}"
        ) from e
    except URLError as e:
        raise RuntimeError(f"ClickUp API network error ({method} {path}): {e}") from e


# ---------------------------------------------------------------------------
# CLI — `python -m tools.clickup {check|get-task}`
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        prog="tools.clickup",
        description="Direct ClickUp API v2 wrapper (bypasses the claude.ai connector).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="Verify auth by fetching the pipeline status task")

    gt = sub.add_parser("get-task", help="Fetch a single task by id")
    gt.add_argument("--task-id", required=True)
    gt.add_argument("--subtasks", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "check":
            resp = get_task(CONTENT_PIPELINE_STATUS_TASK_ID)
            name = resp.get("name") or "<no name>"
            print(f"ok: pipeline status task = {CONTENT_PIPELINE_STATUS_TASK_ID} ({name})")
            return 0
        if args.cmd == "get-task":
            resp = get_task(args.task_id, include_subtasks=args.subtasks)
            print(json.dumps(resp, indent=2, ensure_ascii=False))
            return 0
    except RuntimeError as e:
        print(str(e), file=sys.stderr)
        return 2
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
