---
repo: [wilson, son]
mr: [wilson!2846]
verified_at: 2026-11-27
source: https://app.notion.com/p/4136552a98c981eb96dad08c6466ad2d
---

# Video provider goals on Heimspiel lineups (wilson !2846)

Heimspiel sends no goals. When Heimspiel supplies the lineup, the goals come from the
video provider (SICS/SmrtStats), whose own lineup and events steps do not run on that match.
Merged 2026-11-09 (`e5e70e438`). Related: [Heimspiel lineups in wilson](heimspiel-lineups-wilson-flow.md).

## How it works

All in `server/son/models/match_provider_manager.py`.

`_sync_video_provider_goals_safely(skcr_match)`:

- Returns at once unless the match has a video provider `MatchMatching`, a lineup, and
  `data_collection.lineup_provider` in `METADATA_ONLY_PROVIDERS` (Heimspiel).
- Calls `get_match_details_with_players` on the video provider client. A fetch failure is logged
  and retried on the next pass.
- Full replace in one transaction: `goal=0, own_goal=0` on every `TeamPlayerMatch`, then replay
  each provider `GOAL` event with `period.id < 5` (no penalty shootout goals).
- Each goal goes through `_create_goal_safely`: `_match_scorer_by_shirt_number`, then
  `Events.provider.create_goal`. An unresolved scorer raises `UnknownJerseyNumberError` for the
  operators and that goal is not written.

Two triggers:

- The video provider pass, when that provider is not the lineup source (`not _is_lineup_source`
  and provider in `PROVIDERS_WITH_VIDEO`).
- Right after the Heimspiel lineup step, when `lineups_report.changed`
  (`_sync_goals_after_heimspiel_lineup_change`). Reason: the match can be complete after this pass.

## Known gap — task 4181 (Backlog, not started as of 2026-11-27)

[Task 4181](https://app.notion.com/p/4136552a98c981eb96dad08c6466ad2d), raised in the !2846 review.
No MR and no branch exist.

- Operator fixes the lineup in Gaffer → `lineup_provider` becomes `skillcorner` → the guard above
  returns → a goal that failed with `UnknownJerseyNumberError` is never written.
- Per the ticket: a complete match exits the creation cron early, so a later provider correction
  is not picked up. Operators cannot add a goal in Gaffer.
- Proposal in the ticket: run the sync also on complete matches and on operator-edited lineups
  that started from Heimspiel, write only `goal`/`own_goal`, bound it to a window after kick-off
  (e.g. 7 days) and write only when the goals differ.
- Open question in the ticket: do operators enter goals through the staff `EventsView` API? The
  reset-then-replay would overwrite them.
