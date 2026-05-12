# Polling drafter (test-phase, every 3h)

> **Goal.** Every 3 hours, check daily-state files for ClickUp tasks Nikki has marked done. For each newly-approved one: re-run cannibalization, fetch SERP, generate prose, validate via rubric, push to WordPress as draft.

> **Cron.** `0 */3 * * *` UTC (every 3 hours starting at 00:00 UTC). Phoenix is UTC-7 year-round, so this fires at 17:00, 20:00, 23:00, 02:00, 05:00, 08:00, 11:00, 14:00 Phoenix.

> **Test-phase only.** Replaces the weekly Wednesday job during testing.

---

## State machine

Each `data/runs/_daily/<YYYY-MM-DD>.json` advances:

```
discovered  ->  emitted  ->  approved  ->  drafted
                  ^             ^             ^
                  |             |             |
            (daily idea     (this job,    (this job,
             workflow)       checks       generates +
                             ClickUp)     pushes to WP)
```

This polling job advances states `emitted -> approved -> drafted` in a single run. Idempotent: states already at `drafted` (i.e., `wp_post_id` set) are skipped.

---

## Step-by-step

### 1. List pending approvals

```python
from tools.daily import pending_approvals, pending_drafts

awaiting = pending_approvals()  # emitted, not approved
print(f"awaiting approval: {[s.date for s in awaiting]}")
```

If the list is empty AND `pending_drafts()` is also empty → no work; post a quiet "no-op" comment to status task `86ah3ywyh` (or skip the comment if last run was also no-op).

### 2. For each pending approval: poll ClickUp

> **Connector path:** Uses the **ClickUp claude.ai connector** (uuid `37a27fca`) attached to the routine. The agent resolves `clickup_get_task` to that connector. Direct HTTP to `api.clickup.com` is blocked by the routine sandbox proxy.

```python
from tools.daily import is_task_approved, mark_approved, save_state

for state in pending_approvals():
    response = clickup_get_task(
        task_id=state.clickup_task_id,
        detail_level="summary",
    )
    approved, status_name = is_task_approved(response)
    if approved:
        mark_approved(state, status_name=status_name)
        save_state(state)
```

`is_task_approved` returns True for any of the canonical done states:
- ClickUp status `type` field `in {"done", "closed"}`, OR
- Status name in `{"published", "complete", "closed", "done", "ready"}`

### 3. For each pending draft: full draft + push cycle

```python
from tools.daily import pending_drafts, mark_drafted, save_state
from tools.draft import prepare_brief, assemble
from tools.inventory import load as load_inventory
from tools.push_wp import build_create_payload
from tools.rank_math import build_meta
from tools.rubric import FaqItem
from tools.slate import SlateProposal

inv = load_inventory()
inv.assert_fresh()
inv.assert_complete()

for state in pending_drafts():
    # Reconstruct the SlateProposal from the persisted dict
    prop = SlateProposal(**state.proposal)

    # Re-run cannibalization (defense in depth)
    brief = prepare_brief(prop, inv)

    # Fetch SERP intent
    serp = mcp__ahrefs__serp-overview(
        keyword=prop.focus_keyword,
        country="us",
        select="title,url,position,domain_rating,backlinks,traffic,top_keyword",
        top_positions=10,
    )

    # Generate prose (Claude in this agent context)
    Skill(skill="firstmovers-blog-rubric")
    body_html = "<p>...</p>"  # 2,500-3,500 word body Claude writes
    faq_items = [FaqItem(question="...", answer="...") for _ in range(5)]
    seo_title = "..."  # ≤60 chars, focus_kw + power word
    meta_description = "..."  # ≤155 chars, focus_kw

    # Assemble + validate (raises RubricViolation on any rule failure)
    assembled = assemble(
        brief, body_html=body_html, faq_items=faq_items,
        seo_title=seo_title, meta_description=meta_description,
    )

    # Push to WP
    push_payload = build_create_payload(
        title=assembled.title, content=assembled.body_html,
        slug=assembled.slug, excerpt=assembled.excerpt,
        category_id=assembled.category_id,
    )
    wp_response = mcp__claude_ai_FirstMoversWP__wp_create_post(
        title=push_payload.title,
        content=push_payload.content,
        excerpt=push_payload.excerpt,
        status="draft",
        categories=push_payload.categories,
        post_author=3,  # Josh McCoy
    )
    post_id = int(wp_response["id"])
    edit_url = f"https://firstmovers.ai/wp-admin/post.php?post={post_id}&action=edit"

    # Set Rank Math meta
    rm = build_meta(
        focus_keyword=assembled.focus_keyword,
        seo_title=assembled.seo_title,
        meta_description=assembled.meta_description,
        slug=assembled.slug,
    )
    for key, value in [
        ("rank_math_focus_keyword", rm.focus_keyword),
        ("rank_math_title", rm.seo_title),
        ("rank_math_description", rm.meta_description),
    ]:
        mcp__claude_ai_FirstMoversWP__wp_update_post_meta(
            post_id=post_id, key=key, value=value,
        )

    # Update state + comment back on ClickUp
    mark_drafted(state, post_id=post_id, edit_url=edit_url)
    save_state(state)

    clickup_create_task_comment(
        task_id=state.clickup_task_id,
        comment_text=(
            f"Drafted to WordPress.\n\n"
            f"- Edit: {edit_url}\n"
            f"- Preview: https://firstmovers.ai/?p={post_id}&preview=true\n"
            f"- Word count: {len(assembled.body_html.split()):,}\n"
            f"- Author: Josh McCoy\n\n"
            f"Nikki: review, set the slug if needed (canonical: {assembled.slug}), "
            f"add featured image, get Josh CTA approval, publish, NitroPack purge."
        ),
    )
```

### 4. Status comment on the pipeline status task

```python
clickup_create_task_comment(
    task_id="86ah3ywyh",
    comment_text=(
        f"Polling drafter run @ {now_iso}: "
        f"{newly_approved_count} newly approved, "
        f"{drafted_count} drafted, "
        f"{still_awaiting_count} still awaiting approval."
    ),
)
```

---

## Edge cases

- **Already drafted.** State has `wp_post_id` set → skip silently. Idempotent.
- **Cannibalization re-check fails (defense in depth).** A topic that was clear when emitted may now overlap a freshly-published post. `prepare_brief` raises `CannibalizationError`. Mark the state with a note, comment on the ClickUp task explaining the conflict, do not push.
- **Rubric validation fails.** `assemble()` raises `RubricViolation` with the named rule. Re-generate the prose with the failure as feedback. Cap retries at 2 attempts per state per run; on third failure mark with a note and skip until next run.
- **WAF blocks WP push.** Queue to `data/runs/_pending-push/` and trigger the GH Actions Path B workflow. State remains in `approved` (not `drafted`) until the push lands.
- **ClickUp task deleted between emit and poll.** `clickup_get_task` returns 404; treat as "not approved" and continue. Operator manually reconciles if needed.

## Failure modes that page

- All pending drafts fail rubric validation 3 runs in a row → likely model regression
- WP push WAF-blocked AND GH Actions Path B not triggering → infrastructure issue
- Polling cron silently failing (last successful state advance >24h ago) → check the cron registration on the agent host
