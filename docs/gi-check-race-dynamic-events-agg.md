---
repo: [football, skcr-utils, wilson]
mr: [football!1734, skcr-utils!207]
verified_at: 2026-11-24
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
- Fix (football !1734 + skcr-utils !207): `minutes_and_quality_check` outputs `{gi_check_passed}` (QC
  `dynamic_events_v3_check`, null when skipped) → GI v3 / main pass it to `dynamic_events_agg` (optional input,
  Choice IsPresent, default null) → each of the 7 aggregate lambdas has a local payload field `gi_check_passed` and
  calls ONE method, `AbstractFootballPipelineHandler.resolve_gi_check_passed(DataCollection, VideoDataCollection)`
  (payload value, else the DB; son models injected because skcr-utils has no son dependency). Lambda locks pin the
  skcr-utils prerelease until !207 is released (2.33.0), then repin.
- QA (mr-1734, match 2261, dev): standalone and QC-skipped runs follow the DB; the clean proof is DB=True with the
  real QC=False → outputs False (the SFN value wins; a DB read would give True). Not run: the inlined GI chain in
  `main` (static only) and the `Core Events Skipped` path.
- QC for 2261 returned False on 2026-11-24 but True on 2026-11-13 (cause not investigated; main moved 22 commits).
  A QA oracle must compare with the QC value in the SFN history, not with an assumed True.
- Prod backfill (read-only finder, 2026-11-24): source = prod S3 `skcr-football-data-raw-us-prod/gi/metrics/<key>/csv/
  <match_id>.csv.gz` column `GI_METRICS_REP_5365` vs `api_datacollection.dynamic_events_v2_check` (maldini re-reads the
  same S3 file). Of 19,627 matches since 2026-09-01: 151 output False/DB True (the bug), 4 reverse, 81 no DB check,
  1,407 video matches without output by design (`skip_evaluation` skips aggregates when `video_provider` is set).
  Rerun with `francli football run-sfn dynamic_events_agg --env prod --file <batch>` (50 ids per file) only after
  !1734 is on prod, one batch at a time. Scripts and lists: `~/.cache/skillcorner-dev/race-dynamic-events-agg/backfill/`.
  Related: [GI v3 skip path](gi-v3-core-events-skipped-stale-gi.md).
