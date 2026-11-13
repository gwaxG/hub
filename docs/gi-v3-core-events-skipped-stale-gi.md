---
repo: [football, wilson, event-synchronization-gi]
verified_at: 2026-11-04
---

# GI v3 "Core Events Skipped" publishes stale GI (and why player swaps trigger it)

- `pulumi/aws/main/game_intelligence_v3/step_function_config.yaml`: `Shots Goals Sync OK?` →
  `events_ready=false` → `Core Events Skipped` (a `Pass` state) → **`Dynamic Events Aggregate`** (since
  af2dc8b61, 2026-07-07). This path skips auto events, predictive models, DE generation/attributes and
  `Minutes and Quality Check`.
- `events_ready=false` is set by the shots_goals_sync sub-SFN when the lambda returns `Failure`
  (critical exceptions: `WyscoutPlayerIdException`, `MissingWyscoutIdError`, `ProviderPlayerIdException`,
  `PlayerInLineUpWithoutExtrapolationError`, `NegativePeriodStartEstimationException`, `HTTPError`).
  Minor or no-events cases return `Success`, so the run continues normally.
- Only `minutes_and_quality_check/gi_quality_check` writes `dynamic_events_v2_check` /
  `dynamic_events_v3_check` (+ `_last_modified`). On the skip path, the previous value (possibly `True`)
  survives.
- `dynamic_events_agg/skip_evaluation` skips the run only if the DE files are missing, or if
  `video_provider` is set. It never compares the DE files against the current `match_data.json`, so the
  aggregators re-aggregate old CSVs and publish `GiMetricsAggregatedEvent` with a fresh timestamp.
- Wyscout mapping: event-synchronization-gi `events/get_formatted_wyscout_events.py` maps
  `wyscout_to_skc_ply` from `match_data.players[].wyscout_id` (which comes from the wilson Wyscout
  `PlayerMatching`). Wyscout ids that appear in events but not in the lineup go to `error_in_id`, which
  raises `WyscoutPlayerIdException`.
- How a Gaffer lineup swap triggers it: `gaffer/serializers/matches/match_lineup_sync.py` re-creates the
  TeamPlayerMatch but leaves the Wyscout `PlayerMatching` on the removed player. The relaunch then
  raises `WyscoutPlayerIdException`, the run takes the skip path, and the stale GI is published.
  Incident: 2035091 (145500 → 1031933, Wyscout 725232), 2026-11-03. Swaps that are never relaunched
  (2049183, 2044041) keep the old id in match_data and the DE outputs.
- Existing fix tool for identity corrections (duplicates): wilson
  `api/consistency/duplicates.py::fix_duplicated_player`. It moves the PlayerMatching, unlinks Events,
  bumps `DataCollection.last_modified` and invokes the `replace_player_in_data` lambda (eu-central-1),
  which rewrites the ids in S3 for each match where the old player played. No full relaunch is needed.
- **Fix: wilson!2829 (open, son 0.94.1)**, together with the Gaffer TO_RERUN flag
  ([gaffer-lineup-swap-rerun](gaffer-lineup-swap-rerun.md)). wilson!2830 was closed and folded into it;
  Notion ticket 4108 is Done. The football skip path itself is unchanged and still re-aggregates stale CSVs.
- The reset (`son/models/match.py::_reset_dynamic_events_checks`): once the launch lambda accepts a full run,
  `Match._launch_football_pipeline_lambda` resets `dynamic_events_v2/v3_check` to `None`. The run's
  quality check sets them again, and a skipped run leaves "not processed", which the DE API
  (`dynamic_events_views.py`) refuses to serve. A failed launch keeps the flags, and
  `relaunch_match_step` does not reset them. Wilson cannot detect the sync failure from events
  instead: `CoreEventsSyncedEvent` looks the same for a failure and a benign "no external events"
  run (`used=False`, no provider).
- Closed, rejected by the user as too large for a minor fix: football!1695. Description kept for reference:
  `Core Events Skipped` is now a Task invoking `football-gi_quality_check` with
  `core_events_skipped: true`. That flag returns before any read and fails the check with the same
  `GiQualityCheckedEvent` (`passed=False`, variants v2+v3) that wilson maps to
  `dynamic_events_*_check` (`son/domain_events_mapping.py`). The state is followed by an SNS publish,
  then End, so no aggregation runs. Both copies of the branch were changed: the
  `game_intelligence_v3` SFN and the inline one in `pulumi/aws/main/step_function_config.yaml`. The
  lambda is bumped to 1.1.0 and gets its first `tests/` (CI discovers lambdas with a non-empty
  `tests/`, via `cicd/generate_ci_build_jobs.py::has_tests`). Locally, its import needs AWS creds
  (`AWS_PROFILE=Production.Skcr-Software-Common-Role`, `PYTHONPATH=.`).
- Not done (the ticket was closed without them): a staleness guard in `dynamic_events_agg/skip_evaluation` (DE older than
  match_data, or DE player ids not in match_data) for standalone aggregate relaunches, and the
  wilson-side swap handling.
