# Wednesday draft job (Phase 0b)

> **Goal.** By Wednesday 09:00 Phoenix, push WordPress drafts for the titles Nikki approved on Sunday's slate, and reply on the slate task with edit URLs.

> **Schedule.** Cron `0 16 * * 3 UTC` (Wed 09:00 America/Phoenix).

This is the agent contract. Run as a `/schedule` agent.

---

## Inputs

- Current week, e.g. `2026-W22`.
- Slate JSON at `data/runs/_title-slates/2026-W22.json` (written Sunday).
- ClickUp parent task ID (recorded on the Sunday status comment).

---

## Step-by-step

### 1. Verify environment + load slate

```python
from tools.slate import load_slate
from tools.inventory import load as load_inventory

slate = load_slate("2026-W22")
inventory = load_inventory()
inventory.assert_fresh()
inventory.assert_complete()
```

If inventory is stale, refresh first.

### 2. Read approvals from ClickUp

```python
parent_response = mcp__claude_ai_ClickUp__clickup_get_task(
    task_id="<parent_id from Sunday status comment>",
    include_subtasks=True,
)

from tools.clickup import parse_approved_subtasks, filter_proposals_by_approval

approved = parse_approved_subtasks(parent_response)
approved_proposals = filter_proposals_by_approval(slate, approved, max_approvals=7)
```

If `approved_proposals` is empty, post a status comment "No approvals for {week} — skipping draft generation. Titles roll into next Sunday's pool." and exit.

### 3. For each approved proposal: prepare brief, write prose, validate, push

```python
from tools.draft import prepare_brief, render_brief_for_prompt, assemble, write_drafts
from tools.images import parse_pexels_response
from tools.rubric import FaqItem
from tools.push_wp import build_create_payload, parse_create_response, is_waf_block, queue_for_path_b, PendingPush
from tools.rank_math import build_meta, to_payload, endpoint_url

assembled_drafts = []
edit_urls = {}
rank_math_set_count = 0

for proposal in approved_proposals:
    # 3a. Re-run cannibalization (defense in depth — inventory may have grown
    # since Sunday). prepare_brief raises CannibalizationError on critical/high.
    brief = prepare_brief(proposal, inventory, target_word_count=2500)

    # 3b. Fetch SERP intent (for the model writing the prose).
    serp = mcp__ahrefs__serp-overview(keyword=proposal.focus_keyword, country="us")

    # 3c. Fetch 4 Pexels images.
    pexels_raw = <call Pexels API or use mcp__playwright__... for visual research>
    images = parse_pexels_response(pexels_raw, focus_keyword=proposal.focus_keyword)
    if len(images) < 4:
        post_status(f"only {len(images)} images for {proposal.focus_keyword}; skipping")
        continue

    # 3d. Load the rubric skill.
    Skill(skill="firstmovers-blog-rubric")

    # 3e. Generate prose.
    # Pass render_brief_for_prompt(brief) + the SERP overview as your input.
    # Write back: body_html (final HTML), faq_items (3-8 FaqItem records),
    # seo_title (≤60 chars, contains focus_kw + power word), meta_description (≤155 chars).
    body_html = "<p>...</p>"  # the prose Claude writes
    faq_items = [FaqItem(question="...", answer="...") for _ in range(5)]
    seo_title = f"<focus kw>: <power word> 2026 Guide"
    meta_description = "<focus kw> ... (≤155 chars)"

    # 3f. Assemble + validate. Raises RubricViolation on any rule failure.
    assembled = assemble(
        brief,
        body_html=body_html,
        faq_items=faq_items,
        images=images,
        seo_title=seo_title,
        meta_description=meta_description,
    )
    assembled_drafts.append(assembled)

    # 3g. Push to WordPress.
    payload = build_create_payload(
        title=assembled.title,
        content=assembled.body_html,
        slug=assembled.slug,
        excerpt=assembled.excerpt,
        category_id=assembled.category_id,
    )
    rank_math = build_meta(
        focus_keyword=assembled.focus_keyword,
        seo_title=assembled.seo_title,
        meta_description=assembled.meta_description,
        slug=assembled.slug,
    )

    # Try MCP first
    try:
        mcp_resp = mcp__first-movers-wordpress__wp_add_post(
            title=payload.title,
            content=payload.content,
            slug=payload.slug,
            excerpt=payload.excerpt,
            status=payload.status,
            categories=payload.categories,
        )
        result = parse_create_response(mcp_resp)
        if result is None:
            raise RuntimeError(f"unparseable response: {mcp_resp}")
    except Exception as e:
        if is_waf_block(e):
            queue_for_path_b(
                PendingPush(
                    payload=payload,
                    rank_math_meta=to_payload(0, rank_math)["meta"],
                    week=slate.week,
                ),
            )
            print(f"WAF blocked {proposal.focus_keyword}; queued to Path B")
            continue
        raise

    pid = result["id"]
    edit_urls[assembled.focus_keyword] = result["edit_url"]

    # 3h. Set Rank Math meta via the Devora plugin endpoint.
    rank_math_payload = to_payload(pid, rank_math)
    rank_math_response = <POST to endpoint_url() with HTTP basic auth (FM_WP_USER + FM_WP_APP_PASSWORD)>
    if rank_math_response.ok:
        rank_math_set_count += 1
```

### 4. Persist + reply

```python
write_drafts(slate.week, assembled_drafts)

# If any drafts were queued to Path B, trigger the GH Actions workflow:
import subprocess
subprocess.run(["gh", "workflow", "run", "wp-push-fallback.yml", "--ref", "main"])

# Reply on the slate parent task with edit URLs.
from tools.clickup import build_edit_url_reply
reply = build_edit_url_reply(slate.week, edit_urls, rank_math_set_count=rank_math_set_count)
mcp__claude_ai_ClickUp__clickup_create_task_comment(
    task_id="<parent_id>",
    comment_text=reply,
)
```

### 5. Done

Nikki sees the comment with edit URLs. She reviews each draft in WP admin, uploads a featured image, fills affiliate URLs, gets Josh CTA approval, and publishes. The draft order across the week is her call.

---

## Edge cases

- **A title flips to critical/high cannibalization between Sunday and Wednesday.** `prepare_brief` raises `CannibalizationError`. Skip the title, comment why, do not push. Preserve the rest.
- **Rubric violation.** `assemble` raises `RubricViolation` with the named rule. Fix the prose (rewrite the failing piece) and retry. Never silence — the rule is tied to a real Rank Math grade or Josh review failure.
- **WAF block on every push.** Trigger the GH Actions workflow once at the end (single trigger handles every queued draft). Include the workflow run URL in the slate-task reply.
- **`mcp__ahrefs__serp-overview` rate-limited.** Wait 60s and retry; this is read-only and idempotent.

## Failure modes that page

- `DegradedInventoryError` — inventory regenerated since Sunday but came back malformed. Page Aditya.
- All 7 push attempts WAF-blocked AND the GH Actions trigger failed. Page Aditya — Path B is the only unblock.
