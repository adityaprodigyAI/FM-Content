"""clickup — emit slate task + read subtask approvals.

The agent makes the actual MCP calls; this module produces the payloads
and parses the responses. Same separation as inventory_refresh — pure data
transforms, easy to test.

Approval mechanism: parent task with one subtask per slate proposal.
A subtask with `status_type == "done"` (i.e., status name like "complete",
"closed", "published") is considered approved. Phase 0b reads via
`mcp__claude_ai_ClickUp__clickup_get_task` with `include_subtasks=True`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from .identities import (
    CONTENT_PIPELINE_STATUS_TASK_ID,
    CONTENT_PROJECTS_LIST_ID,
    NIKKI_CLICKUP_USER_ID,
)
from .slate import Slate, SlateProposal


# ClickUp API call shapes Claude will make. Recorded here so the Sunday
# agent has a single reference and the test suite can assert payload
# correctness without hitting the network.

DONE_STATUS_TYPES: Final[frozenset[str]] = frozenset({"done", "closed"})


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
        status = st.get("status") or {}
        status_type = ""
        if isinstance(status, dict):
            status_type = str(status.get("type") or "").strip().lower()
        if status_type not in DONE_STATUS_TYPES:
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
