# `/schedule` registration — daily-idea + polling-drafter cron

> Copy-paste invocations to register the two FM-Content cron routines via Claude Code's `/schedule` skill. Each routine is a remote Claude agent that runs on cron with your MCP credentials attached (WordPress, ClickUp, Ahrefs, GSC, GitHub).

## TL;DR

Run `/schedule` in Claude Code twice — once per routine. Use the cron expressions, names, and prompts below.

| Routine name | Cron (UTC) | Phoenix time | Purpose |
|---|---|---|---|
| `fm-content-daily-idea` | `0 14 * * *` | 07:00 daily | Pick one new topic, emit ClickUp task for Nikki |
| `fm-content-poll-and-draft` | `0 */3 * * *` | every 3h | Detect approvals, generate prose, push WP drafts |

After the user marks any daily task `published` in ClickUp, the polling drafter picks it up within 3 hours and produces a fully validated WordPress draft.

---

## Routine 1 — `fm-content-daily-idea`

**Cron:** `0 14 * * *` UTC (07:00 America/Phoenix, fixed offset UTC-7 year-round)

**Name:** `fm-content-daily-idea`

**Prompt** (paste this verbatim):

```text
You are running the FM-Content pipeline's daily-idea routine. Today's job is to
pick ONE new content topic and emit it as a ClickUp task for Nikki to approve.

Repository: https://github.com/adityaprodigyAI/FM-Content (branch: main)
Workflow contract: workflows/content-daily-idea.md (READ THIS FIRST and follow
it exactly. The instructions below are a summary, not a replacement.)

SETUP
  git clone https://github.com/adityaprodigyAI/FM-Content.git fm-content
  cd fm-content
  pip install -e .

  TODAY="$(python -c 'from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo("America/Phoenix")).strftime("%Y-%m-%d"))')"
  DOW="$(python -c 'from datetime import datetime; from zoneinfo import ZoneInfo; print(datetime.now(ZoneInfo("America/Phoenix")).strftime("%A"))')"

STEPS
  1. Idempotency: if data/runs/_daily/${TODAY}.json exists, post comment to
     ClickUp task 86ah3ywyh: "Daily idea ${TODAY}: already emitted, skipping."
     and exit 0.

  2. Inventory freshness:
       python -m tools.inventory_refresh --check
     If exit 1 (stale) or 2 (missing), refresh per workflows/content-inventory-
     refresh.md before continuing.

  3. Discovery — call MCPs and parse:
       gsc = mcp__gsc__get_search_analytics(
         site_url="sc-domain:firstmovers.ai",
         dimensions="query,page", days=28, row_limit=200)
       Rotated competitor for ${DOW}:
         Monday    -> mckinsey.com
         Tuesday   -> bcg.com
         Wednesday -> bain.com
         Thursday  -> hubspot.com
         Friday    -> accenture.com
         Saturday  -> deloitte.com
         Sunday    -> mckinsey.com
       ahrefs = mcp__ahrefs__site-explorer-organic-keywords(
         target=<rotated competitor>, mode="subdomains", date=${TODAY},
         select="keyword,best_position,best_position_url,sum_traffic,volume,keyword_difficulty",
         limit=100, order_by="sum_traffic:desc")

  4. Filter + pick top-1 (Python in the repo):
       from tools.discover.gsc import discover as gsc_discover
       from tools.discover.ahrefs_gap import discover as ahrefs_discover
       from tools.daily import pick_top_candidate, candidate_to_proposal_dict
       from tools.cannibalization import ProposedTopic, evaluate
       from tools.inventory import load
       inv = load(); inv.assert_fresh(); inv.assert_complete()
       gsc_cands = gsc_discover(<gsc>, inv)
       translated = [{"keyword": kw["keyword"], "volume": kw["volume"],
                      "difficulty": kw["keyword_difficulty"],
                      "position": kw["best_position"],
                      "traffic": kw["sum_traffic"]}
                     for kw in <ahrefs>["keywords"]]
       ahrefs_cands = ahrefs_discover(<competitor>, {"keywords": translated}, inv)
       all_cands = gsc_cands + ahrefs_cands
       clear = []
       for c in all_cands:
         topic = ProposedTopic(slug=c.focus_keyword.lower().replace(" ", "-"),
                               title=c.suggested_title_seed,
                               focus_keyword=c.focus_keyword,
                               category_id=c.category_id,
                               audience=c.audience)
         if evaluate(topic, inv).severity not in ("critical", "high"):
           clear.append(c)
       top = pick_top_candidate(clear)
       if top is None:
         comment 86ah3ywyh "Daily idea ${TODAY}: no clear candidates from
         <competitor>. Will retry tomorrow with rotated competitor." and exit 0.

  5. Generate working_title (≤120 chars, no trailing period, no em dashes,
     no "free audit"), one-line angle, three H2-starter outline bullets.

  6. Save daily state:
       from tools.daily import DailyState, save_state
       proposal = candidate_to_proposal_dict(top, title=<title>, angle=<angle>,
                                              outline=<outline>, target_date=TODAY)
       state = DailyState(date=TODAY, proposal=proposal); save_state(state)

  7. Emit ONE top-level ClickUp task:
       resp = mcp__claude_ai_ClickUp__clickup_create_task(
         list_id="901326229295",
         name=f"[{TODAY}] {proposal['working_title']}",
         markdown_description=<rich description with focus_kw, audience, category,
                               intent, target_date, angle, outline bullets,
                               discovery evidence>,
         assignees=["26221739"],   # Nikki Martinez
         due_date=TODAY,
         tags=["fm-content-daily"])
       state = mark_emitted(state, task_id=resp["task_id"]); save_state(state)

  8. Status comment:
       mcp__claude_ai_ClickUp__clickup_create_task_comment(
         task_id="86ah3ywyh",
         comment_text=f"Daily idea {TODAY} emitted: {proposal['working_title']!r} "
                      f"(focus_kw: {proposal['focus_keyword']}, "
                      f"score: {proposal['score']:.2f}, "
                      f"source: {proposal['discovery_source']}). "
                      f"ClickUp: https://app.clickup.com/t/{resp['task_id']}")

  9. Persist state to repo:
       git config user.name  "fm-content[bot]"
       git config user.email "fm-content-bot@firstmovers.ai"
       git add data/runs/_daily/
       git commit -m "chore(daily): emit ${TODAY} ${proposal['focus_keyword']}"
       git push

HARD RULES (per CLAUDE.md, never bypass)
  - status=draft on creation; Nikki is the only publish gate
  - author=Josh McCoy (WP user 3)
  - no "free audit" anywhere
  - no em dashes (hyphens only)
  - audience routing: done-for-you -> /consulting/; diy -> /labs/

ON FAILURE
  - Post a status comment to ClickUp task 86ah3ywyh describing what failed
  - Exit non-zero so the cron host logs the failure
  - Do not retry destructive actions (no double-emit on any task)
```

---

## Routine 2 — `fm-content-poll-and-draft`

**Cron:** `0 */3 * * *` UTC (every 3 hours starting 00:00 UTC; in Phoenix that fires at 17:00, 20:00, 23:00, 02:00, 05:00, 08:00, 11:00, 14:00)

**Name:** `fm-content-poll-and-draft`

**Prompt** (paste this verbatim):

```text
You are running the FM-Content pipeline's polling drafter. Every 3 hours you
check for ClickUp tasks Nikki has approved and generate WordPress drafts.

Repository: https://github.com/adityaprodigyAI/FM-Content (branch: main)
Workflow contract: workflows/content-poll-and-draft.md (READ THIS FIRST and
follow it exactly. The instructions below are a summary, not a replacement.)

SETUP
  git clone https://github.com/adityaprodigyAI/FM-Content.git fm-content
  cd fm-content
  pip install -e .

STEPS
  1. List pending work:
       python -m tools.daily pending-approvals
       python -m tools.daily pending-drafts
     If both lists are empty, exit 0 silently (do not spam the status task).

  2. For each pending approval:
       resp = mcp__claude_ai_ClickUp__clickup_get_task(
         task_id=state.clickup_task_id, detail_level="summary")
       from tools.daily import is_task_approved, mark_approved, save_state
       approved, status_name = is_task_approved(resp)
       if approved:
         mark_approved(state, status_name=status_name)
         save_state(state)

  3. For each pending draft (approved-but-undrafted state):
       from tools.slate import SlateProposal
       from tools.draft import prepare_brief, assemble
       from tools.inventory import load
       from tools.rubric import FaqItem
       from tools.push_wp import build_create_payload
       from tools.rank_math import build_meta
       from tools.daily import mark_drafted

       inv = load(); inv.assert_fresh(); inv.assert_complete()
       prop = SlateProposal(**state.proposal)
       brief = prepare_brief(prop, inv)   # cannibalization re-check

       serp = mcp__ahrefs__serp-overview(
         keyword=prop.focus_keyword, country="us",
         select="title,url,position,domain_rating,backlinks,traffic,top_keyword",
         top_positions=10)

       Skill(skill="firstmovers-blog-rubric")

       # Generate body_html (2500-3500 words, 7 H2s, focus_kw in lede + ≥1 H2,
       # ≥3 external dofollow citations from external_links.curated_for, no
       # em dashes, no "free audit", FAQ NOT in body — assemble adds it),
       # faq_items (3-7 FaqItem records), seo_title (≤60 chars with power
       # word + focus_kw + year), meta_description (≤155 chars with focus_kw)
       body_html = "<p>...</p>"
       faq_items = [FaqItem(question="...", answer="...") for _ in range(5)]
       seo_title = "..."
       meta_description = "..."

       try:
         assembled = assemble(brief, body_html=body_html, faq_items=faq_items,
                               seo_title=seo_title, meta_description=meta_description)
       except RubricViolation as e:
         # Re-generate prose addressing the failed rule (max 2 retries)
         continue / retry

       wp = mcp__claude_ai_FirstMoversWP__wp_create_post(
         title=assembled.title, content=assembled.body_html,
         excerpt=assembled.excerpt, status="draft",
         categories=[assembled.category_id], post_author=3)
       post_id = int(wp["id"])
       edit_url = f"https://firstmovers.ai/wp-admin/post.php?post={post_id}&action=edit"

       rm = build_meta(focus_keyword=assembled.focus_keyword,
                       seo_title=assembled.seo_title,
                       meta_description=assembled.meta_description,
                       slug=assembled.slug)
       for k, v in [("rank_math_focus_keyword", rm.focus_keyword),
                    ("rank_math_title", rm.seo_title),
                    ("rank_math_description", rm.meta_description)]:
         mcp__claude_ai_FirstMoversWP__wp_update_post_meta(
           post_id=post_id, key=k, value=v)

       mark_drafted(state, post_id=post_id, edit_url=edit_url); save_state(state)

       mcp__claude_ai_ClickUp__clickup_create_task_comment(
         task_id=state.clickup_task_id,
         comment_text=f"Drafted to WordPress.\n\n"
                      f"- Edit: {edit_url}\n"
                      f"- Preview: https://firstmovers.ai/?p={post_id}&preview=true\n"
                      f"- Word count: {len(assembled.body_html.split()):,}\n"
                      f"- Author: Josh McCoy (post_author=3)\n\n"
                      f"Nikki: review, set slug to '{assembled.slug}' if needed, "
                      f"add featured image, get Josh CTA approval, publish, "
                      f"NitroPack purge.")

  4. Final status comment (only if any state advanced):
       mcp__claude_ai_ClickUp__clickup_create_task_comment(
         task_id="86ah3ywyh",
         comment_text=f"Polling drafter run: <N> newly approved, "
                      f"<M> drafted, <K> still awaiting approval.")

  5. Persist state to repo:
       git config user.name  "fm-content[bot]"
       git config user.email "fm-content-bot@firstmovers.ai"
       git add data/runs/_daily/
       if git diff --cached --quiet; then
         echo "no state changes"
       else
         git commit -m "chore(daily): poll+draft run $(date -u +%Y-%m-%dT%H:%MZ)"
         git push
       fi

FAILURE HANDLING
  - CannibalizationError on prepare_brief: a topic that was clear at emit
    now overlaps a freshly-published post. Add a note to state.notes,
    comment on the ClickUp task explaining the conflict, skip the draft.
  - RubricViolation on assemble: regenerate the prose addressing the
    named rule. Cap at 2 retries per state per run. On third failure,
    add a note and skip until next run.
  - WAF block on wp_create_post (HTTP 403 / Wordfence in the response):
    queue to data/runs/_pending-push/<slug>.json (tools.push_wp.queue_for_path_b),
    trigger the wp-push-fallback.yml workflow via:
        gh workflow run wp-push-fallback.yml --ref main
    Leave state at 'approved' (not 'drafted') — next run picks it up
    after the GH Actions push completes and writes wp_post_id back.

HARD RULES (never bypass)
  - status=draft on creation
  - author=Josh McCoy (WP user 3) — pass post_author=3 explicitly
  - no "free audit" anywhere
  - no em dashes (hyphens only)
  - no trailing period in titles
  - audience CTAs: done-for-you -> /consulting/; diy -> /labs/
  - 19 rubric checks in tools/rubric.py — all must pass
  - cannibalization gate: critical/high severity is a hard block

IDEMPOTENCY
  - State already DRAFTED (wp_post_id set) -> skip silently
  - State PENDING (no clickup_task_id) -> skip (the daily-idea routine
    handles those)
```

---

## After registration

Verify both routines are registered:

```
/schedule list
```

You should see:
```
fm-content-daily-idea       0 14 * * *      next: 2026-05-10 14:00 UTC
fm-content-poll-and-draft   0 */3 * * *     next: <upcoming :00>
```

The daily-idea routine fires once tomorrow morning Phoenix time. The polling drafter fires every 3 hours and is a no-op until the daily routine emits the first task and Nikki approves it.

## Switching back to weekly mode later

When you're ready to leave testing and go to the production weekly cycle:

```
/schedule delete fm-content-daily-idea
/schedule delete fm-content-poll-and-draft
/schedule create  ...  # use workflows/content-sunday-slate.md   (cron 0 14 * * 0)
/schedule create  ...  # use workflows/content-wednesday-draft.md (cron 0 16 * * 3)
```

The daily mode does not interfere with the weekly mode — they share state files in `data/runs/_daily/` and `data/runs/_title-slates/` respectively. Switching is just a matter of which routines are registered.
