---
name: fm-wordpress-push
description: Use when pushing a validated draft to WordPress as status=draft, setting Rank Math meta, or handling WAF blocks via the Path B fallback. Covers wp_create_post payload assembly, Rank Math meta keys, post_author=3, valid category IDs, and the GH Actions WAF-bypass workflow.
verified: 2026-05-12
---

# WordPress push

The terminal step of the pipeline: turn a validated `AssembledDraft` into a WordPress post with `status="draft"` so Nikki can review and publish.

## Hard rules (enforced by `tools/push_wp.py`)

| Rule | Why | Where enforced |
|---|---|---|
| `status="draft"` always | Only Nikki publishes | `build_create_payload` |
| `post_author=3` (Josh McCoy) | Single source of truth, `tools/identities.py::WP_AUTHOR_JOSH` | `build_create_payload` |
| Category in `VALID_WP_CATEGORY_IDS` ({27, 28, 29, 30, 13, 14, 10}) | Hand-curated | `_validate_category_id` |
| Endpoint host must be `firstmovers.ai` | No accidental cross-site pushes | `_assert_host` |

## The push call

    from tools.push_wp import build_create_payload
    from tools.rank_math import build_meta

    payload = build_create_payload(
        title=assembled.title,
        content=assembled.body_html,
        slug=assembled.slug,
        excerpt=assembled.excerpt,
        category_id=assembled.category_id,
    )

    wp = wp_create_post(
        title=payload.title,
        content=payload.content,
        excerpt=payload.excerpt,
        slug=payload.slug,
        status="draft",
        categories=payload.categories,
        post_author=3,
    )
    post_id = int(wp["id"])

## Rank Math meta

After post creation, set three Rank Math meta keys:

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
        wp_update_post_meta(post_id=post_id, key=key, value=value)

`rank_math_title` and `rank_math_description` override the WP default title/excerpt for SERP rendering. `rank_math_focus_keyword` powers the 19-check rubric grading inside the WP admin.

## Featured image

In v1: left blank. Nikki adds it post-publish. Do NOT call `wp_set_featured_image` from the pipeline.

## WAF fallback (Path B)

The Cloudways WAF intermittently blocks REST POST to `/wp-json/wp/v2/posts`. Symptom: 403 with body like `"Your request was blocked. Please contact support."`

Detection + queue:

    from tools.push_wp import queue_for_path_b, is_waf_block

    try:
        wp = wp_create_post(...)
    except Exception as e:
        if is_waf_block(e):
            queue_for_path_b(assembled, target_dir="data/runs/_pending-push/")
            # leave state at 'approved', not 'drafted'
            subprocess.run(["gh", "workflow", "run", "wp-push-fallback.yml", "--ref", "main"])
            return
        raise

Path B runs from GitHub Actions (different egress IP, bypasses the WAF rule).

## Audience routing reminder

Audience routing (DFY → /consulting/, DIY → /labs/) is enforced upstream in `tools.draft.assemble`. By the time we get to push_wp the CTA is already correct. See `firstmovers-blog-rubric` §9 for the canonical mapping.

## Post-push: comment on the ClickUp task

After successful push, comment on the daily-state's ClickUp task:

    Skill(skill="fm-clickup-ops")

    clickup_create_task_comment(
        task_id=state.clickup_task_id,
        comment_text=(
            f"Drafted to WordPress.\n\n"
            f"- Edit: https://firstmovers.ai/wp-admin/post.php?post={post_id}&action=edit\n"
            f"- Preview: https://firstmovers.ai/?p={post_id}&preview=true\n"
            f"- Word count: {wc:,}\n"
            f"- Author: Josh McCoy (post_author=3)\n\n"
            f"Nikki: review, set slug if needed ({assembled.slug}), add featured image, "
            f"get Josh CTA approval, publish, NitroPack purge."
        ),
    )

## Failure modes

| Symptom | Diagnosis |
|---|---|
| `403 "Your request was blocked"` | WAF. Queue to Path B. |
| `400 "invalid_param" for categories` | Category not in `VALID_WP_CATEGORY_IDS`. Check `tools/identities.py`. |
| `401 Unauthorized` | App password expired or revoked in WP admin. Regenerate. |
| Post created but Rank Math meta missing | `wp_update_post_meta` failed silently; retry, then verify in WP admin |
| Post `post_author` is 1 (admin) not 3 | `post_author=3` not passed to `wp_create_post`. Always pass explicitly. |

## See also

- `firstmovers-blog-rubric` — audience routing + valid categories canonical
- `fm-clickup-ops` — the post-push notification pattern
- `fm-prose-generation` — the step before push
