---
name: fm-clickup-ops
description: Use when creating ClickUp tasks for Nikki, polling task status for approvals, or commenting on the pipeline status task. Covers task-creation patterns, approval semantics, workspace/list/user IDs from tools/identities.py, and when to comment vs not.
verified: 2026-05-12
---

# ClickUp operations

ClickUp is the human-loop surface. Three operations matter: **create** (daily idea emit), **read** (approval polling), **comment** (status + traceability).

## Canonical IDs

From `tools/identities.py`:

| Name | ID | Purpose |
|---|---|---|
| Workspace | `9013404166` | Top-level team |
| List: Content Projects | `901326229295` | Where daily-idea tasks land |
| Task: Pipeline Status | `86ah3ywyh` | Heartbeat / status comment sink |
| User: Nikki | `26221739` | Assignee for daily-idea tasks |
| User: Josh | `120239313` | CTA approver (informational, not assigned) |

Always import from `tools.identities`, NEVER hardcode in workflows or skills.

## Create a daily task

    resp = clickup_create_task(
        list_id="901326229295",
        name=f"[{today}] {proposal['working_title']}",
        markdown_description=<rich block with proposal details + evidence>,
        assignees=[26221739],   # Nikki
        due_date=today,         # YYYY-MM-DD; ClickUp accepts ISO date string
        tags=["fm-content-daily"],
    )
    task_id = resp.get("task_id") or resp.get("id")

The `markdown_description` block should contain:
- Focus keyword
- Working title
- Audience (DFY or DIY)
- Discovery source + evidence
- Estimated traffic / KD / volume
- Cannibalization gate result

This is what Nikki reads to decide approve/decline.

## Poll for approval

    resp = clickup_get_task(task_id=state.clickup_task_id, detail_level="summary")
    from tools.daily import is_task_approved
    approved, status_name = is_task_approved(resp)

`is_task_approved` returns `True` if:
- Status `type` field in `{"done", "closed"}`, OR
- Status `name` in `{"published", "complete", "closed", "done", "ready"}` (case-insensitive)

This handles ClickUp workspace variability where teams customize status names.

## Comment patterns

### When to comment

| Event | Comment on | What |
|---|---|---|
| Routine start (canary) | `86ah3ywyh` | `"Routine X started at <iso>"` — only if there's pending work, else suppress |
| Daily idea emitted | new task | Auto-handled by `clickup_create_task` body |
| Approval polled successfully | `state.clickup_task_id` | (no comment — silent mark_approved is fine) |
| Draft pushed to WP | `state.clickup_task_id` | Full comment with edit URL, preview URL, word count, post-publish checklist |
| Cannibalization conflict at draft time | `state.clickup_task_id` | Explain the conflict; do NOT push the draft |
| Rubric violation 3x in a row | `state.clickup_task_id` | Note the violated rule; skip until next polling cycle |
| Run summary | `86ah3ywyh` | Only when state actually advanced — silent no-op runs don't comment |
| Cloud-routine duplicate detected (dual-mode) | `86ah3ywyh` | `"Daily idea {today}: cloud routine already emitted task {id}; mirrored to local state."` |

### Don't comment

- Idempotent skips (already drafted) — silent
- Empty runs (no pending work) — silent (or one daily no-op comment at most)
- Diagnostic / debug info — log to disk, don't pollute ClickUp

## Status task `86ah3ywyh` — the canary

This is the central pipeline-health signal. Comments here are read by operators (Aditya) NOT by Nikki.

Use it for:
- Routine start / end heartbeat
- Run summaries ("Polling drafter run: 1 newly approved, 1 drafted, 2 still awaiting")
- Failure reports (with full traceback)
- Drift alerts (inventory >7 days old, etc.)

## Failure modes

| Symptom | Diagnosis |
|---|---|
| `404` on `clickup_get_task` | Task deleted between emit and poll. Treat as not-approved; continue. |
| Comment lands but assignee field is empty on the task | Wrong assignee ID. Check `tools.identities.NIKKI_CLICKUP_ID`. |
| Status name customized to "Approved" | Add it to `is_task_approved`'s accepted set; commit + push. |
| `401 Unauthorized` (direct REST only) | `CLICKUP_API_TOKEN` expired. Regenerate from ClickUp settings. |

## See also

- `firstmovers-blog-rubric` — what gets put in the task description
- `fm-wordpress-push` — the post-push comment pattern
