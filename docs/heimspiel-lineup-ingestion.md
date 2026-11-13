---
repo: [data-provider-clients, wilson]
mr: [data-provider-clients!34, data-provider-clients!48, wilson!2540]
verified_at: 2026-11-12
---

# Heimspiel lineup & instruction ingestion (task 807)

Spec: Notion "Lineup and instruction ingestion from Heimspiel" (rewritten 2026-10-16).

## dpc side — `feat/heimspiel-lineup-spec`, dpc !48 → 1.16.0
- `heimspiel/lineup.py` `TeamLineup` builds each team: starters (`tactical` + Mapping Formation
  via `tactical_formation_id`/`pos_index`, else `lineup` events), then bench (all, incl. never
  came on), then players seen only in `substitute-in` (`person` on / `additional_person` off).
- < 11 starters: a player whose first event is going off is rebuilt as a starter (12511593 Sadusky).
- Positions (spec 2026-10-20): formation-table position only if the team has `tactical_formation`
  and the starter's `pos_index` maps; everyone else `SUB` (subs, no formation e.g. NCAA, no slot), per team.
- `shirtnumber` 0 → None. `additional_person` carries no shirt; looked up from other events.
- Events: only Substitution + Red Card (`red`, `yellow-red`); red card to non-lineup person dropped.
- Timing: `time` ('HH:MM:SS') exact; else `minute - 1 + extra_minute`, second 0.
  Raw field is `extra_minute` (90+4 → minute 90, extra_minute 4). Capped period-end minute
  without it → `Approximate Time` tag on the Event.
- Event minutes are period-relative (`_PERIOD_OFFSETS`), so 2/46 → period 2, 0:00.

## History
- dpc !34 (`feat/heimspiel-lineup-events`, old spec: drop minute-only events) landed on main as
  b1151cc (1.15.0) although the MR shows "closed".
- wilson !2540 merged 2026-11-03 (squash `0c54f47c5`, son 0.91.0, dpc 1.16.3) — wilson-side
  behaviour in [heimspiel-lineups-wilson-flow](heimspiel-lineups-wilson-flow.md).

## Open: minute-only matches → "Instructions timestamps review" (task 4059, To Do)
Source: Slack https://skillcorner.slack.com/archives/C04GQ2WFH6V/p1794496554241369 (2026-11-12).
- Problem: since dpc 1.16, a minute-only sub/red card is placed at `minute-1`:00, which can't be told apart
  from an exact time (`Approximate Time` is set only on a capped period end, and wilson never reads it).
- Options: A = keep the time + tag every rounded event `Approximate Time` and store the tag in wilson;
  B (Marthe's preference) = create the event with no frame, so it isn't pushed to Vidic and launch stays blocked until the operator re-times it,
  and re-ingestion must not overwrite that work. Both need dpc to tag all non-`time` events.
- Ticket flow: the match skips the Home Team Side queue, and the operator fixes the timestamps, sets the HTS and launches it from the match page,
  so the HTS check still happens. The billing count (does it count like HTSV?) is still open, per Slack.
