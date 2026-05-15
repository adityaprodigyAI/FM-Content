# /loop migration cutover log

> Track daily over 7 days to validate the /loop runtime before disabling the legacy /schedule routines.

| Date | /loop daily fired? | /schedule daily fired? | /loop polling fired? | Tasks emitted (should be 1/day) | WP drafts pushed | Notes |
|---|---|---|---|---|---|---|
| 2026-05-13 | | | | | | |
| 2026-05-14 | | | | | | |
| 2026-05-15 | | | | | | |
| 2026-05-16 | | | | | | |
| 2026-05-17 | | | | | | |
| 2026-05-18 | | | | | | |
| 2026-05-19 | | | | | | |

## Pass criteria (to disable /schedule)

- 7 consecutive days where /loop fires when Claude Code is open and emits exactly 1 daily task
- At least 3 successful end-to-end runs (idea → approval → WP draft)
- Zero double-emissions (state-file + ClickUp idempotency hold)
- Heartbeat fires every 12h without spurious alerts
- Days when Claude Code is closed: heartbeat detects the gap and posts an alert within 36h

## Issues observed

(append as encountered)

## Decision

On 2026-05-20 or later, after the 7-day window:

- PASS: Disable both legacy /schedule routines. Keep heartbeat /schedule active.
- FAIL: Extend observation by another 7 days, surface issues to the team, retry.
