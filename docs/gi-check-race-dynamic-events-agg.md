---
repo: [football, wilson]
verified_at: 2026-11-13
---

# GI check race: dynamic_events_agg reads dynamic_events_v2_check before wilson writes it

- Since football `f451572bb` (2026-09-14), `minutes_and_quality_check` no longer writes the GI check to the DB:
  `GI quality check` → `Publish Domain Event` (SNS `game_intelligence.quality_checked`) → SQS
  `wilson-domain-events-{env}` → wilson `apply_domain_events` (cold start 10-19 s) writes
  `DataCollection.dynamic_events_v2_check` / `v3_check`.
- `game_intelligence_v3` runs `Minutes and Quality Check` (nested `startExecution.sync:2`, `ResultPath: null`,
  output discarded) then immediately `Dynamic Events Aggregate`. Its 7 `aggregate_*` lambdas (obr, po, obe, pa,
  pa_epv, pp, pp_epv; no shared module) each read `dynamic_events_v2_check` from the DB and stamp it on every
  player as `gi_check_passed` → stale/empty → all False, maldini hides GI (match 2091826, Notion task 4226).
- The `gi_quality_check` lambda returns the value as `update_data_collection_kwargs.dynamic_events_v2_check`
  (v2 == v3 there); there is no `match_level_gi_qc` key in its output.
- Gotchas for any fix: the GI chain is duplicated inline in `pulumi/aws/main/step_function_config.yaml`; the minutes
  SFN `to_skip` branch has no `$.result`; `Core Events Skipped` has no fresh check; dynamic_events_agg's
  `Kwargs update` Pass drops extra input keys and lambda payloads read `$$.Execution.Input`; francli run-sfn /
  wilson relaunch / `dynamic_events_epv_historical_recompute` start it without any check → keep a DB fallback.
- Same async-write pattern, lower risk (larger gap): `get_gi_quality_index` reads
  `tracking_extra_v3_*_quality_index`; `get_shot_goal_synchro_details` reads `gi_*_event_provider_used`.
- Fix in progress: football branch `fix/gi-check-race-dynamic-events-agg` — pass `gi_check_passed` through the
  SFNs, lambdas fall back to the DB when absent. Related: [GI v3 skip path](gi-v3-core-events-skipped-stale-gi.md).
