---
repo: [data-provider-clients, wilson]
mr: [shared/data-provider-clients!57, software/wilson!2878]
verified_at: 2026-11-13
---

# Heimspiel imprecise instruction timing

Heimspiel sometimes gives only the minute of a `substitute-in` / `red`, not the second.
Since data-provider-clients 1.16 such an event is placed at the start of the previous minute
("68'" → 67:00, intentional: Heimspiel sends the current minute) with no tag. `Approximate Time` is set
only for capped period ends (45/90/105/120 without `time` / `extra_minute`): the event is really somewhere
in added time but is placed at 44:00/89:00. Wilson did not read the tag.

Decision (Slack C04GQ2WFH6V thread 1794496554.241369, Nov 2026, Marthe/Andrei/Louis):

1. Ingestion (Notion task 4228, Andrei): dpc emits two tags, `Minute Precision` and `Approximate Time`;
   events with neither `time` nor `minute` are no longer rejected. Wilson stores `timing_precision`
   on the instruction (`null` exact / `minute` / `period_end` / `reviewed`), creates flagged events at
   the given minute as a pre-fill, creates untimed ones without frame, and never pushes flagged or untimed
   instructions to Vidic. Rule: an instruction in Vidic is either exactly timed or absent.
2. Matches with an event still "to verify" go to Gaffer `Instructions timestamps review` and launch is
   blocked (parent ticket, Marthe).
3. Ops validation/realignment switches the event to provider `skillcorner` (no longer overwritten by
   Heimspiel re-ingestion) and pushes it to Vidic (parent ticket).

Heimspiel event creation in Wilson exists since 03/11/2026 (wilson!2540, task 807) but was not yet activated.

## Implementation (task 4228, Nov 2026)

- dpc!57 (1.17.0): `Minute Precision` (minute only, at (N-1):00) / `Approximate Time` (capped, checked
  against the resolved period); untimed events returned with `start/end_minute/second = None`; shoot-out
  (period 5) events without `time` dropped. Common `Event` timing fields are `int | None`.
- wilson!2878 (son 0.99.0, migration 0286): `Events.timing_precision` = null / `minute` / `period_end` /
  `untimed` / `reviewed`. Untimed → `frame=None`, no `match_time`, TPM times untouched. Vidic push excludes
  `minute`/`period_end`/`untimed`. Red-card dedup includes the player; reentry/sub-out checks skip null frames.
- Deploy wilson (migration) before relocking the Heimspiel lambdas; relock before activating any Heimspiel CE.

## What the Heimspiel events step needs (learned in the e2e on stack mr-2878)

- The CE beating must have `create_matches_from_heimspiel_active` **and** `create_lineups_from_heimspiel`
  (otherwise Heimspiel is not the lineup source and lineup/events steps are `ignored`). No CE had the second
  flag on a fresh stack.
- The lineup step must succeed: `PotentialDuplicatePlayersFoundError` (two SKCR players with similar names, no
  Heimspiel PlayerMatching) leaves events `to_create`. Fix = create the Heimspiel `PlayerMatching`.
- Period-start rows must exist: `get_frame_and_time` does `Events.objects.get(period_N start)`, so without
  periods the step errors with `DoesNotExist` and is retried. Periods come from the video provider; a match
  recreated from Heimspiel alone has none.
- Deleting a match: `Events.match` is `on_delete=PROTECT` — delete its events first.
- Result seen: NCAA subs stored `minute`, frame = period start + (N-1)·60·10 fps, events complete, no Vidic push.
