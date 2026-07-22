---
title: Heimspiel extra time & penalty shootouts
type: interface
status: current
systems: [data-provider-clients]
last_verified: 2026-07-17
---

# Heimspiel: extra time & penalty shootouts

How Heimspiel represents knockout matches that go beyond 90 minutes, and how to
read them from the `data-provider-clients` Heimspiel client.

> Source repo lives outside the hub root at `../skcr/data-provider-clients`.
> Key files: `src/data_provider_clients/football/models/heimspiel/match_result_at.py`
> and `src/data_provider_clients/football/heimspiel/client.py`.

There are **two independent data sources**, and you need both to fully understand
such a match:

1. **Result periods** (`match_result`) — cumulative scoreline *snapshots*.
2. **Match events** (`match_event`, only via `get_match_details` / `raw_match`) —
   the play-by-play, including every extra-time incident and every penalty kick.

---

## 1. Result periods — `match_result` / `match_result_at`

Each match carries a list of `match_result` rows. Each row is tagged with a
`match_result_at` period code, catalogued at `/match-result-at/sp1`. There are
**only four codes** (modelled by `MatchResultPeriod` in
`models/heimspiel/match_result_at.py`):

| code (`match_result_at`) | `MatchResultPeriod` | meaning |
|--------------------------|---------------------|---------|
| `'0'`  | `FINAL`             | **Final result** — folds in the penalty shootout when there was one |
| `'1'`  | `AFTER_FIRST_HALF`  | cumulative score after the 1st half |
| `'2'`  | `AFTER_SECOND_HALF` | cumulative score after the 2nd half (i.e. after 90') |
| `'21'` | `AFTER_EXTRA_TIME`  | cumulative score after extra time (**before penalties**) |

The numbering (`0, 1, 2, 21`) is Heimspiel's internal scheme — there is nothing
between `2` and `21`. `display_order` is `10/20/30/40`, which is the intended
sequence: final → 1st half → 2nd half → extra time.

Each period has a `home` and `away` row (the `place` field; sometimes prefixed,
e.g. `none_home` in World Cup data).

### Pre-penalty score

When a match goes to a shootout, the official final result (`'0'`) is the
**post-shootout** score. The real, on-pitch result is the after-extra-time
period (`'21'`). The client exposes this:

- `Match.home_score` / `away_score` — always the official final (`'0'`).
- `Match.home_score_pre_penalty` / `away_score_pre_penalty` — the `'21'` score
  when it exists, else `None`.

**Rule:** a `'21'` row exists **iff** the match went to extra time. Penalties
only ever follow extra time, so `'21'` present ⇒ possible shootout; if
`'0' != '21'`, a shootout happened and the difference is the shootout tally.

Verified example (FA Cup 2025/26, match `11666813`): after 2nd half `1-1`,
after ET `1-1`, final `4-2` → true score 1-1, shootout 4-2.

> ⚠️ Result periods do **not** tell you *what* happened during extra time — only
> the running score at each boundary. For incidents, use the event stream.

---

## 2. Match events — extra time & the shootout

`match_event` (populated by `get_match_details` / accessible raw via
`raw_match`) contains structural markers and per-incident events. The `period`
field distinguishes the phases:

| `period` | phase |
|----------|-------|
| `'1'` | 1st half |
| `'2'` | 2nd half |
| `'3'` | 1st half of extra time (91'–105') |
| `'4'` | 2nd half of extra time (106'–120') |
| `'5'` | penalty shootout |

### Structural markers (`action = 'match'`)

These bound each phase (they are not "events" in the football sense, and the
client deliberately does not map them):

```
match / first-extra-start    min=91  period=3
match / first-extra-end      min=105 period=3
match / second-extra-start   min=106 period=4
match / second-extra-end     min=120 period=4
match / penalty-start        min=120 period=5
match / game-end             period=5
```

### Extra-time incidents

Normal incidents during ET (`goal`, `card`, `playing/substitute-in`) appear with
`period='3'` or `'4'` and minutes in the 91–120 range — same shape as
regulation-time events.

### Penalty kicks (`action = 'pso'`)

Each kick in the shootout is one event:

- `action = 'pso'`
- `kind = 'goal'` or `kind = 'miss'`
- `period = '5'`, `minute = '120'`
- `team_id` = the team taking the kick

Counting `pso`/`goal` per `team_id` reconciles with the shootout tally implied
by `'0'` minus `'21'`. Example (DFB-Pokal 2025/26, match `11142261`): `pso`
goals 7 (team 528) vs 8 (team 2076) → final `7-8`, after-ET `4-4`.

---

## Current client behaviour (as of `data-provider-clients` v1.9.3)

- ✅ Pre-penalty score is exposed (`home_score_pre_penalty` / `away_score_pre_penalty`).
- ✅ Extra-time goals/cards/subs are emitted as common `Event`s.
- ⚠️ **`pso` kicks are dropped.** `_EVENT_MAP` / `_classify_event` in
  `heimspiel/client.py` only map goal/card/substitution, so shootout kicks do
  not appear in the common event list, and there is no shootout-tally field on
  `Match`.
- ⚠️ `_resolve_period` caps at period 4 and `_PERIOD_OFFSETS` stop at 105', so a
  period-5 event would be bucketed as period 4 (cosmetic; no pso events reach
  this path today anyway).

If per-kick shootout events or a shootout tally are needed later, that is where
to extend: add `pso` handling to the event mapping and/or a
`home_shootout_score` field on the common `Match`.
