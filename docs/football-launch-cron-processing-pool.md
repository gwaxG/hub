---
repo: [wilson, football]
mr: [wilson!2664, football!1575, wilson!2818, football!1680, skcr-models!81]
verified_at: 2026-11-04
---

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
football !1575 makes the cron skip a future match: it returns without launching, and the row stays in the pool.

## Moving the MatchBeating writes to Wilson (ADR 0011, open as of 2026-11-04)

`task_by_row_v2` writes `MatchBeating` (`started_at`, then in `finally` `last_try`, `started_at=None`, plus `done=True` on success).
That made it the last Football writer. With `WILSON_DB_READONLY` set (wilson!2795), every launch failed (Sentry FOOTBALL-29V), and football!1660 reverted it.
The plan: Football selects the match read-only and publishes `pipeline.launch_attempted` `{succeeded}` (skcr-models!81, football!1680).
Wilson's `apply_domain_events` maps it to `Target.MATCH_BEATING`: `last_try=occurred_at`, `started_at=None`, `done=True` on success, and it creates the row if missing (wilson!2818).
Accepted risks: no timestamp gate, so a late event can mark a re-queued match done. A lost event leaves `last_try` unchanged and pins the queue head; the DLQ alarm detects it and a redrive fixes it.

**Rollout rule:** the `apply_domain_events` lambda image installs `son` from the private registry, using its own `uv.lock` and not `server/`.
A new `Target` in `server/son/domain_events_mapping.py` is referenced in `app.py`'s `_HANDLERS` at import. If the locked son lacks it, the import fails and **every** event dead-letters.
The `server/` tests use local son, so CI stays green. Order: release son, bump the lambda's `son` pin and relock, then deploy.
