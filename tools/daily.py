"""daily — test-phase daily-idea + every-3h polling drafter.

Replaces the weekly Sunday/Wednesday cycle with:
  - Daily ideation: top-1 candidate selection + single ClickUp task emit
  - Polling drafter: every-3h check for approved tasks + draft generation

Each daily candidate gets its own JSON state file at
`data/runs/_daily/<YYYY-MM-DD>.json`. State machine:

    discovered  -> emitted_to_clickup -> approved -> drafted -> pushed_to_wp

The pipeline progresses each day's state forward independently. The polling
drafter is idempotent — it skips states already drafted (`wp_post_id` set).

Pure state management + lookups; LLM/MCP work runs in the agent context
described by `workflows/content-daily-idea.md` and
`workflows/content-poll-and-draft.md`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Final

from .discover import SOURCE_WEIGHTS, Candidate
from .identities import CONTENT_PROJECTS_LIST_ID
from .slate import SlateProposal, _slug_from_focus_keyword

DAILY_DIR: Final[Path] = (
    Path(__file__).resolve().parents[1] / "data" / "runs" / "_daily"
)


# ---------------------------------------------------------------------------
# State record (one per day)
# ---------------------------------------------------------------------------


@dataclass
class DailyState:
    """The full state for one day's idea, advancing through the pipeline."""

    date: str                              # YYYY-MM-DD
    proposal: dict[str, Any]               # asdict(SlateProposal)
    clickup_task_id: str | None = None
    clickup_emitted_at: str | None = None  # ISO-8601 UTC
    approved_at: str | None = None         # ISO-8601 UTC, set when polling sees done status
    approved_status_name: str | None = None  # the ClickUp status name that triggered approval
    wp_post_id: int | None = None
    wp_edit_url: str | None = None
    drafted_at: str | None = None          # ISO-8601 UTC
    rejected_at: str | None = None         # ISO-8601 UTC, set when polling sees a reject status
    rejected_status_name: str | None = None  # the ClickUp status name that triggered rejection
    notes: list[str] = field(default_factory=list)

    @property
    def is_emitted(self) -> bool:
        return bool(self.clickup_task_id)

    @property
    def is_approved(self) -> bool:
        return bool(self.approved_at)

    @property
    def is_drafted(self) -> bool:
        return bool(self.wp_post_id)

    @property
    def is_rejected(self) -> bool:
        return bool(self.rejected_at)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def state_path(d: str | date, dir_: Path = DAILY_DIR) -> Path:
    s = d.isoformat() if isinstance(d, date) else str(d)
    return dir_ / f"{s}.json"


def load_state(d: str | date, dir_: Path = DAILY_DIR) -> DailyState | None:
    p = state_path(d, dir_)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return DailyState(**data)


def save_state(state: DailyState, dir_: Path = DAILY_DIR) -> Path:
    dir_.mkdir(parents=True, exist_ok=True)
    p = state_path(state.date, dir_)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(asdict(state), fh, ensure_ascii=False, indent=2)
    tmp.replace(p)
    return p


_DAILY_FILENAME_RE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}\.json$")


def list_states(dir_: Path = DAILY_DIR) -> list[DailyState]:
    """Load every active daily-state file.

    Only filenames matching the strict ``YYYY-MM-DD.json`` pattern count.
    This excludes archived/renamed files (e.g., ``2026-05-09.test-archive.json``
    or ``2026-05-12.test-archive-pre-e2e.json``) which would otherwise re-enter
    the pipeline as ``pending_approval`` states and cause duplicate drafts.
    """
    if not dir_.exists():
        return []
    out: list[DailyState] = []
    for p in sorted(dir_.glob("*.json")):
        if not _DAILY_FILENAME_RE.match(p.name):
            continue
        try:
            with p.open(encoding="utf-8") as fh:
                data = json.load(fh)
            out.append(DailyState(**data))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    return out


def pending_approvals(dir_: Path = DAILY_DIR) -> list[DailyState]:
    """States emitted to ClickUp but not yet approved.

    These are the tasks the polling drafter calls `clickup_get_task` on
    every 3 hours.
    """
    return [
        s for s in list_states(dir_)
        if s.is_emitted and not s.is_approved and not s.is_rejected
    ]


def pending_drafts(dir_: Path = DAILY_DIR) -> list[DailyState]:
    """States approved but not yet drafted.

    These are the tasks the polling drafter generates prose for.
    """
    return [
        s for s in list_states(dir_)
        if s.is_approved and not s.is_drafted and not s.is_rejected
    ]


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------


def pick_top_candidate(candidates: list[Candidate]) -> Candidate | None:
    """Return the source-weighted top-1 candidate, or None if empty."""
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda c: c.score * SOURCE_WEIGHTS.get(c.discovery_source, 1.0),
    )


def candidate_to_proposal_dict(
    cand: Candidate,
    *,
    title: str,
    angle: str,
    outline: list[str],
    target_date: str,
) -> dict[str, Any]:
    """Wrap a Candidate as a SlateProposal-shaped dict for state persistence."""
    proposal = SlateProposal(
        focus_keyword=cand.focus_keyword,
        working_title=title,
        one_line_angle=angle,
        outline_bullets=outline,
        slug=_slug_from_focus_keyword(cand.focus_keyword),
        audience=cand.audience,
        category_id=cand.category_id,
        intent=cand.intent,
        target_date=target_date,
        discovery_source=cand.discovery_source,
        discovery_id=cand.discovery_id,
        discovery_evidence=dict(cand.discovery_evidence),
        score=cand.score,
    )
    return asdict(proposal)


# ---------------------------------------------------------------------------
# Approval detection — leverages the existing parse_approved_subtasks logic
# ---------------------------------------------------------------------------


def is_task_approved(clickup_task_response: Any) -> tuple[bool, str | None]:
    """Inspect a `mcp__claude_ai_ClickUp__clickup_get_task` response and
    return (is_approved, status_name).

    Handles both response shapes:
      - top-level task: status is a rich object with .type
      - via subtasks=true: status is a bare string

    Reuses the same DONE_STATUS_TYPES / DONE_STATUS_NAMES contract as
    `clickup.parse_approved_subtasks`.
    """
    from .clickup import _is_subtask_done  # noqa: PLC0415 — avoid circular at import

    if not isinstance(clickup_task_response, dict):
        return False, None
    status = clickup_task_response.get("status")
    name = ""
    if isinstance(status, dict):
        name = str(status.get("status") or "").strip()
    elif isinstance(status, str):
        name = status.strip()
    return _is_subtask_done(status), name or None


def is_task_rejected(clickup_task_response: Any) -> tuple[bool, str | None]:
    """Inspect a `clickup_get_task` response and return (is_rejected, status_name).

    Mirrors `is_task_approved` but uses the rejection allowlist in
    `tools.clickup` (`_is_subtask_rejected`). Callers should check
    `is_task_rejected` BEFORE `is_task_approved` so that an explicit
    rejection wins over an ambiguous approval — and so that a state
    already approved can still be overridden when the operator changes
    the ClickUp status to a reject-type one.
    """
    from .clickup import _is_subtask_rejected  # noqa: PLC0415 — avoid circular at import

    if not isinstance(clickup_task_response, dict):
        return False, None
    status = clickup_task_response.get("status")
    name = ""
    if isinstance(status, dict):
        name = str(status.get("status") or "").strip()
    elif isinstance(status, str):
        name = status.strip()
    return _is_subtask_rejected(status), name or None


def mark_emitted(state: DailyState, *, task_id: str) -> DailyState:
    state.clickup_task_id = task_id
    state.clickup_emitted_at = _now_iso()
    return state


def mark_approved(state: DailyState, *, status_name: str | None = None) -> DailyState:
    state.approved_at = _now_iso()
    state.approved_status_name = status_name
    return state


def mark_rejected(state: DailyState, *, status_name: str | None = None) -> DailyState:
    """Mark the state as rejected — terminal, never drafts.

    Overrides any prior approval: a state that was approved then rejected
    will not appear in `pending_drafts`. The `approved_at` timestamp is
    preserved on disk as part of the audit trail.
    """
    state.rejected_at = _now_iso()
    state.rejected_status_name = status_name
    return state


def mark_drafted(
    state: DailyState,
    *,
    post_id: int,
    edit_url: str | None = None,
) -> DailyState:
    state.wp_post_id = int(post_id)
    state.wp_edit_url = edit_url
    state.drafted_at = _now_iso()
    return state


# ---------------------------------------------------------------------------
# CLI — `python -m tools.daily {status|pending-approvals|pending-drafts}`
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.daily")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="Print all daily states (full state map)")
    sub.add_parser("pending-approvals",
                   help="Print states emitted to ClickUp but not yet approved")
    sub.add_parser("pending-drafts",
                   help="Print states approved but not yet drafted (polling drafter target)")

    show = sub.add_parser("show", help="Print one day's state JSON")
    show.add_argument("date", help="YYYY-MM-DD")

    args = parser.parse_args(argv)

    if args.cmd == "status":
        states = list_states()
        if not states:
            print("(no daily states)")
            return 0
        for s in states:
            print(_format_state_summary(s))
        return 0

    if args.cmd == "pending-approvals":
        for s in pending_approvals():
            print(_format_state_summary(s))
        return 0

    if args.cmd == "pending-drafts":
        for s in pending_drafts():
            print(_format_state_summary(s))
        return 0

    if args.cmd == "show":
        s = load_state(args.date)
        if s is None:
            print(f"no state for {args.date}", file=sys.stderr)
            return 2
        print(json.dumps(asdict(s), indent=2, ensure_ascii=False))
        return 0

    parser.print_help()
    return 0


# ---------------------------------------------------------------------------
# Dual-mode safety: ClickUp-side idempotency check
# ---------------------------------------------------------------------------
#
# During the 7-day cutover window where both the legacy `/schedule` cloud
# routine and the new `/loop` local routine fire on the same day, the local
# state file in `data/runs/_daily/<DATE>.json` cannot prevent the cloud
# routine from emitting a duplicate task (the cloud routine has no access to
# the local disk). This helper queries ClickUp for an existing daily-idea
# task tagged `fm-content-daily` with name starting `[<today>]`. If found,
# the caller should mirror that task id into local state and skip emit.
#
# Remove this helper (and its call site in workflows/content-daily-idea-loop.md)
# after the cutover window closes and the cloud routines are disabled.


def should_skip_for_clickup_dup(
    today: str,
    clickup_search_fn,
) -> tuple[bool, str | None]:
    """Check ClickUp for an existing daily-idea task for `today`.

    Args:
        today: YYYY-MM-DD date string in operator's working timezone (Phoenix).
        clickup_search_fn: Callable that takes ClickUp search kwargs and
            returns a dict with a "tasks" list. Pass the MCP tool
            `clickup_search` from the agent context, or a `tools.clickup`
            wrapper for local testing.

    Returns:
        (skip, task_id):
            skip=True means a duplicate already exists for today and the
            caller should NOT emit a new task. task_id is the existing
            ClickUp id to mirror into local state.
            skip=False means no duplicate; proceed with normal emit flow.
    """
    prefix = f"[{today}]"
    resp = clickup_search_fn(
        list_id=CONTENT_PROJECTS_LIST_ID,
        tags=["fm-content-daily"],
        order_by="created",
        reverse=True,
        limit=5,
    )
    for task in resp.get("tasks", []):
        if not task.get("name", "").startswith(prefix):
            continue
        tag_names = {t.get("name") for t in task.get("tags", [])}
        if "fm-content-daily" in tag_names:
            return True, task.get("id")
    return False, None


def _format_state_summary(s: DailyState) -> str:
    icon = (
        "REJECTED" if s.is_rejected
        else "DRAFTED " if s.is_drafted
        else "APPROVED" if s.is_approved
        else "EMITTED " if s.is_emitted
        else "PENDING "
    )
    title = (s.proposal or {}).get("working_title", "<no title>")[:70]
    parts = [f"{s.date}  {icon}  {title}"]
    if s.clickup_task_id:
        parts.append(f"  clickup={s.clickup_task_id}")
    if s.wp_post_id:
        parts.append(f"  wp={s.wp_post_id}")
    return "".join(parts)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(_main())
