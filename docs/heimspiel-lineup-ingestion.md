---
repo: [data-provider-clients, wilson]
mr: [data-provider-clients!34, data-provider-clients!48, wilson!2540]
verified_at: 2026-10-20
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
- wilson !2540 (`feat/lineups-events`, draft) still pins dpc 1.14.1; needs 1.16.0, must not
  expect Heimspiel goals (son raises `UnhandledProviderEvent` on yellow cards).
