# Football launch cron and the processing pool

`football-launch_football_pipeline-<env>` (football repo, `pulumi/aws/standalone/launch_football_pipeline`)
runs `rate(1 minute)` with an empty event, which means `requester='cron'` and an execution name ending `_by_cron`.
`@task_by_row_v2` (wilson `server/son/models/task_by_row.py`) picks **one** Match per run where
`MatchBeating.collect_tracking_data_for_match_active=True`, skipping matches whose `last_try` is under 1h50 old
or whose `started_at` is under 1h20 old. Nulls of `last_try` sort first. If the handler raises, the row stays
active and is retried every 1h50. Before the fix below, only `DataCollection.status not in {not_available, postmatch}` gated it.

Wilson writers of `collect_tracking_data_for_match_active=True` (default False):
- `set_matches_to_retry_online` lambda, via `MatchQuerySet.add_to_queue`, which Forest relaunch actions use. It also sets `status=to_rerun`.
- Forest **Create new dimensions** (`api/forest/stadium.py`) with relaunch: queues all matches of the stadium with
  `date_time >= start_date`, which **included future fixtures**. This is the likely cause of the 2027 matches launched by cron (2075524, 2026-09-24).
- admin `MatchPreprodStatus` save, `tmp_dirty_launch_match`, `scripts/match_full_rewrite.py`.

The Heimspiel stadium-change relaunch (`_relaunch_after_stadium_update`) is a different path:
it acts only on POST_MATCH matches, uses `requester='stadium_update'`, and calls the lambda directly.

Fix (2026-10-01): wilson !2664 makes the dimensions relaunch and `set_matches_to_retry_online` skip or refuse future matches.
football !1575 makes the cron set `active=False` for a future match and return without launching. Raising would keep it active.
