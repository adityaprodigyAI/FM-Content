# Polling drafter — /loop variant (runs in operator's local Claude Code)

> **Goal.** Every 3 hours, check daily-state files for ClickUp tasks the approver has marked done. For each newly-approved one: re-run cannibalization, fetch SERP, generate prose, validate via rubric, push to WordPress as draft.
>
> All client-specific values come from `client_config.toml` via `tools.identities`. This workflow hardcodes none of them.

> **Runtime.** Register with `/loop` inside the operator's local Claude Code session, using `client_config.toml` → `schedule.polling_drafter_local_cron`.

> **Why /loop.** Local MCP access for Ahrefs (`serp-overview`), WordPress (`wp_create_post`), and ClickUp. Future enhancements (e.g., GSC pre-draft sanity check) require local MCP access too.

---

## Step-by-step

### 1. List pending work (silent if empty)

```python
import sys; sys.path.insert(0, ".")
from tools.daily import pending_approvals, pending_drafts
# All client-specific values come from client_config.toml via tools.identities.
from tools.identities import (
    APPROVER_NAME,
    CONTENT_PIPELINE_STATUS_TASK_ID,
    CTA_APPROVER_NAME,
    RUBRIC_SKILL_NAME,
    SITE_BASE_URL,
    WP_AUTHOR_ID,
)

awaiting = pending_approvals()
drafts = pending_drafts()
if not awaiting and not drafts:
    sys.exit(0)
```

### 2. Canary comment

```
Skill(skill="fm-clickup-ops")
```

```python
from datetime import datetime, timezone
now_iso = datetime.now(timezone.utc).isoformat()
clickup_create_task_comment(
    task_id=CONTENT_PIPELINE_STATUS_TASK_ID,
    comment_text=f"Routine fm-content-poll-and-draft started at {now_iso}",
)
```

### 3. Process each pending approval

```python
from tools.daily import is_task_approved, mark_approved, save_state

for state in pending_approvals():
    resp = clickup_get_task(task_id=state.clickup_task_id, detail_level="summary")
    approved, status_name = is_task_approved(resp)
    if approved:
        mark_approved(state, status_name=status_name)
        save_state(state)
```

### 4. Process each pending draft

Load all skills needed for prose + push:

```
Skill(skill=RUBRIC_SKILL_NAME)   # client's blog-rubric skill, from client_config.toml [rubric]
Skill(skill="fm-prose-generation")
Skill(skill="fm-cannibalization")
Skill(skill="fm-wordpress-push")
```

For each pending draft:

```python
from tools.slate import SlateProposal
from tools.draft import prepare_brief, assemble
from tools.inventory import load
from tools.rubric import FaqItem, RubricViolation
from tools.push_wp import build_create_payload
from tools.rank_math import build_meta
from tools.daily import mark_drafted

inv = load(); inv.assert_fresh(); inv.assert_complete()

for state in pending_drafts():
    prop = SlateProposal(**state.proposal)
    brief = prepare_brief(prop, inv)   # cannibalization defense-in-depth re-check

    serp = mcp__ahrefs__serp-overview(
        keyword=prop.focus_keyword, country="us", top_positions=10,
        select="title,url,position,domain_rating,backlinks,traffic,top_keyword",
    )

    # Generate body_html, faq_items, seo_title, meta_description per fm-prose-generation
    body_html = "..."   # 2500-3500 words, ≥6 H2, focus_kw in lede + ≥1 H2
    faq_items = [FaqItem(question="...", answer="...") for _ in range(5)]
    seo_title = "..."   # ≤60 chars, contains focus keyword + power word + number
    meta_description = "..."   # ≤155 chars, contains focus keyword

    # Validate + retry up to 2x
    for attempt in range(3):
        try:
            assembled = assemble(
                brief, body_html=body_html, faq_items=faq_items,
                seo_title=seo_title, meta_description=meta_description,
            )
            break
        except RubricViolation as e:
            if attempt == 2:
                clickup_create_task_comment(
                    task_id=state.clickup_task_id,
                    comment_text=f"Rubric violation after 3 attempts: {e}. Skipping until next poll.",
                )
                continue
            # regenerate prose addressing the named rule (e.message)

    # Push to WP
    payload = build_create_payload(
        title=assembled.title, content=assembled.body_html, slug=assembled.slug,
        excerpt=assembled.excerpt, category_id=assembled.category_id,
    )
    wp = wp_create_post(
        title=payload.title, content=payload.content, excerpt=payload.excerpt,
        slug=payload.slug, status="draft", categories=payload.categories,
        post_author=WP_AUTHOR_ID,
    )
    post_id = int(wp["id"])

    # Rank Math meta
    rm = build_meta(
        focus_keyword=assembled.focus_keyword, seo_title=assembled.seo_title,
        meta_description=assembled.meta_description, slug=assembled.slug,
    )
    for key, value in [
        ("rank_math_focus_keyword", rm.focus_keyword),
        ("rank_math_title", rm.seo_title),
        ("rank_math_description", rm.meta_description),
    ]:
        wp_update_post_meta(post_id=post_id, key=key, value=value)

    edit_url = f"{SITE_BASE_URL}/wp-admin/post.php?post={post_id}&action=edit"
    mark_drafted(state, post_id=post_id, edit_url=edit_url)
    save_state(state)

    wc = len(assembled.body_html.split())
    clickup_create_task_comment(
        task_id=state.clickup_task_id,
        comment_text=(
            f"Drafted to WordPress.\n\n"
            f"- Edit: {edit_url}\n"
            f"- Preview: {SITE_BASE_URL}/?p={post_id}&preview=true\n"
            f"- Word count: {wc:,}\n"
            f"- Author: WordPress user {WP_AUTHOR_ID} (post_author)\n\n"
            f"{APPROVER_NAME}: review, set slug if needed ({assembled.slug}), add featured image, "
            f"get {CTA_APPROVER_NAME} CTA approval, publish, purge any page cache."
        ),
    )
```

### 5. Status comment on the pipeline-status task

```python
clickup_create_task_comment(
    task_id=CONTENT_PIPELINE_STATUS_TASK_ID,
    comment_text=(
        f"Polling drafter run: <N> newly approved, "
        f"<M> drafted, <K> still awaiting."
    ),
)
```

### 6. Commit + push

```python
import subprocess
subprocess.run(["git", "add", "data/runs/_daily/"], check=False)
subprocess.run(["git", "commit", "-m", "chore(daily): polling-drafter advance"], check=False)
subprocess.run(["git", "push"], check=False)
```

## Failure handling

- **CannibalizationError on `prepare_brief`**: comment on the ClickUp task, skip draft, leave state at `approved`. Operator reconciles manually.
- **RubricViolation × 3**: comment, skip until next poll.
- **WAF block on `wp_create_post`**: queue to `data/runs/_pending-push/` via `tools.push_wp.queue_for_path_b`, trigger `wp-push-fallback.yml` via `gh` CLI. Leave state at `approved`.

## Idempotency

- State `drafted` (wp_post_id set) → silent skip
- State `pending` (no clickup_task_id) → silent skip (daily-idea handles it)
- /loop only fires when Claude Code is open; if it's closed at 3h boundary, the next fire after reopening catches up the backlog
