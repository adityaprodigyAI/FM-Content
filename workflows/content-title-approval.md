# Title approval (Nikki-facing SOP)

> **Audience:** Nikki Martinez. Owner of the publish gate.

> **Cadence:** Every Sunday by ~07:30 Phoenix you'll see a new task in your ClickUp inbox: `Approve <week> blog titles by Tue EOD`. The task has 12 subtasks (one per proposed title). You tick up to 7 of them by Tuesday 23:59 Phoenix.

---

## What you'll see

A ClickUp parent task with 12 subtasks. Each subtask shows:

- **Working title** (subtask name)
- **Focus keyword** — the search term we're targeting
- **Audience** — `done-for-you` (links to /consulting/) or `diy` (links to /labs/)
- **Category id** — which WP category the post will land in
- **Target publish date** — the calendar slot
- **Angle** — one line on the angle the draft will take
- **Outline** — three H2 starters
- **Why this topic** — the discovery source (GSC striking-distance, Ahrefs competitor gap, Searchable AEO, GA4 high-traffic gap) + the cannibalization rationale

Every title in the slate has already been verified non-overlapping with our published content. You don't have to re-check that — focus on whether the angle and audience are right for the week.

---

## How to approve

For each title you want drafted on Wednesday: **change the subtask status to "Complete" or "Closed"**. That's it.

Subtasks left in any other status (open, in progress, blocked, etc.) are **NOT** approved.

You can:

- Approve up to **7 titles**. Approve more and Wednesday's job ships every approved one — but Nikki picks publish order downstream.
- Approve **0 titles** if all 12 are weak. The week skips. Unapproved titles roll back into next Sunday's candidate pool.
- Comment on a subtask if you approve the angle but want it tweaked. The Wednesday agent reads task comments before writing prose.

Soft deadline: **Tuesday 23:59 Phoenix**. The Wednesday job fires at 09:00 Phoenix and reads whatever subtask state exists at that moment.

---

## What happens next

Wednesday 09:00 Phoenix, the system:

1. Reads your subtask approvals.
2. Re-runs the cannibalization gate (defense in depth — a competitor or one of our own posts may have published since Sunday).
3. Fetches SERP intent + writes 2,500–3,500 word drafts conforming to the firstmovers-blog-rubric.
4. Pushes the drafts to WordPress as `status=draft`.
5. Posts a comment on the parent slate task with edit URLs for each draft.

You then:

1. Click each edit URL → review the draft.
2. Upload the featured image (Pexels images are hotlinked in the body — they show in the post but don't go to WP Media Library; featured image is yours to set).
3. Fill any affiliate URLs.
4. Get Josh's CTA approval (he reviews destination + wording, not the title).
5. Publish + purge NitroPack cache.

---

## Edge cases

- **A title looks great but the focus keyword feels weird.** Approve it anyway. The Wednesday agent reads task comments — leave a note like "approve, but please reframe focus_keyword as 'AI consulting pricing 2026'."
- **You'd publish only 5 not 7 this week.** Approve 5. Wednesday ships 5 drafts. There's no penalty for fewer.
- **A subtask description references a URL on firstmovers.ai you don't recognize.** Comment on the subtask. The cannibalization gate may have failed silently — don't approve until verified.

---

## When Phase 0a or 0b breaks

The pipeline status task is `https://app.clickup.com/t/86ah3ywyh`. If you see a failure comment there, ping Aditya.
