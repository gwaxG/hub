---
repo: [wilson, football, skcr-models, skcr-utils, skcr-football-utils, francli]
mr: [skcr-models!86, skcr-utils!198, skcr-football-utils!101, francli!539, wilson!2856, football!1718]
verified_at: 2026-11-17
source: https://skillcorner.slack.com/archives/C04GQ2WFH6V/p1794211220857189
---

# Configurable extra time half duration (per CE)

Project "Make extra time duration configurable" (Notion task 4136, owner Andrei;
project lead Mohamed Rahmouni). Not top priority (Nov 2026).

## Why

Pipelines infer extra time half duration from `half_duration`: 45 → 15 min,
40/30 → 10 min. NCAA plays 2x45 + 2x10 (playoffs only; regular season ends in
a draw), so the 2nd ET half starts at 1:45:00 instead of 1:40:00 in tracking,
physical events and dynamic events files. Aggregated physical metrics are not
affected. Agreed to ship NCAA with the caveat and rerun affected matches later
(origin thread: https://skillcorner.slack.com/archives/C0A6EU5K1HV/p1793124712964209).
Youth competitions may also be affected — no list yet. Test matches: 2070668, 2070594.

## Split of work

- **Metadata team (us, first):** `extra_time_half_duration` on CompetitionEdition,
  default 15 if half_duration=45 else 10 (no behaviour change), exposed with match
  metadata, present in the pipeline payload for any run — including partial reruns
  from an intermediate step (e.g. Physical), using the current CE value.
- **Pipeline/data (Pierre Mauron, Paul Nantas, Giulio Fantuzzi):** step functions read
  the new param instead of the rule; adding it to the payload breaks nothing; Tracking
  and GI likely need adaptation. Must not regress golden-goal handling (NCAA ET is golden goal).
- **Backoffice squad (Gaffer; Marthe Brandam, Louis):** set/update the value on CE
  create/edit, default 15, match-level override only if half_duration has one.
  BO spec: https://app.notion.com/p/4106552a98c9801692a4f750d4d0d8f2. Open question:
  prefill 10 when half_duration is set to 40. BO has no bandwidth yet; our ticket goes first.

## Where half_duration lives today (code map, 2026-11-09)

- Storage: not on CE but on `MatchCompetitionEditionRunParameter` (OneToOne to CE),
  `wilson/server/son/models/match_competition_edition_run_parameters.py` (`HalfDuration` 40/45).
  Post-run copy on `DataCollection.half_duration` / `VideoDataCollection.half_duration`.
  No persisted match-level override — only per-launch (`LaunchWithParamsSerializer`).
- Gaffer = wilson `server/gaffer/` (DRF, nested as `processing_parameters`) + Angular
  `software/gaffer-front`. Forest Admin (`api/forest/competition_edition.py`, `match.py`) also edits it.
  `gaffer/core/match_launch.py` hardcodes `MIN_EXTRA_TIME_DURATION_MIN = 15` for the launch period-duration check.
- Domain event: `skcr-models` football `domain_events.py` (strict, `extra='forbid'`) → contract bump.
- Pipeline: `football/pulumi/aws/standalone/start_sfn/utils.py` resolves
  `kwargs.get('half_duration', ce_run_parameters.half_duration)`; defaults also in
  `skcr-utils` / `skcr-football-utils` lambdas utils. Consumers: event_synchro
  (`event-synchronization-private`), quality_metrics, check_data_quality_v3 (`check-data-quality`).
  `extrapolation_v3/extrapolation_tracking_formatting/utils.py` hardcodes 45/90/105 period offsets.
  The 45→15/else→10 rule is NOT in any mirrored repo — likely inside a private lib
  (event-synchronization-private / physical-data-v3 / check-data-quality); per Slack, unverified.
- Partial rerun: `relaunch_match_from_step` lambda → francli starts a fresh main SFN with a
  skip list; every sub-SFN calls `football-start_sfn`, which re-reads CE run params. So reruns
  get the current CE value for free; per-launch overrides are lost (relaunch forwards none).
- No golden-goal code found anywhere.
- Golden goal is a separate problem (Aaron Danino, https://skillcorner.slack.com/archives/C06MXSVUB2N/p1794300612508509):
  NCAA ET can end on a golden goal → 3 periods, or a short ET period. Blockers: `son/pipeline_checks/checks_core.py`
  `check_periods_count` accepts only 2 or 4 period starts (`InconsistentNumberOfPeriodEvents`); Gaffer
  `gaffer/core/match_launch.py` warns on ET periods < `MIN_EXTRA_TIME_DURATION_MIN = 15`. Pipeline support for
  3 periods is unverified.

## Implementation (merged 2026-11-17)

All MRs merged except skcr-football-utils !101 (closed, not needed). Notion task 4136 Done.

- Wilson migration `0288_extra_time_half_duration`: run params, DataCollection and VideoDataCollection
  get `extra_time_half_duration` 10/15, `default` and `db_default` 15, then a RunPython backfill sets 10
  wherever `half_duration != 45`. The `db_default` matters because an older son still inserts rows
  without the column. (An earlier draft used null = follow half_duration; dropped.)
- son 0.101.1, skcr-models 0.39.2 (optional field on `quality_metrics.computed`), skcr-utils 2.30.1
  (`FootballPayloadKwargs` derives the value when None). francli `--extra-time-half-duration 10|15`.
- football `start_sfn/extra_time.py` `resolve_extra_time_half_duration`: launch kwarg > CE value (only
  if half_duration isn't overridden to something else) > None (derived downstream). It stays out of
  `start_sfn/utils.py` on purpose: that module builds `SonSettings` at import (Secrets Manager), which
  the CI test runner cannot read.
- wilson `domain_events_mapping`: `quality_metrics.computed` copies the value to DataCollection only
  when the event carries it.
- Partial reruns (e.g. `--start-at physical_v3`) get the current CE value: `start_sfn` resolves it on
  every launch. `francli --dry-run` does not call `start_sfn`, so it cannot show the resolved value.

## Dev QA (2026-11-17)

wilson `9bcb66a7f` + football `0122a0b4c` on dev, quality_metrics-only reruns, all SFNs SUCCEEDED:
- 2261 (CE unset, half 45): DataCollection 15.
- 2070668 (NCAA, CE 1495 = 10): 10.
- 2070594 (launch `--extra-time-half-duration 15`): 15.

CE 1495 is left at 10 on dev on purpose (PM review).

Restoring dev S3 inputs for a quality_metrics-only rerun: the migrate-and-copy `extrapolation-pipeline`
preset is not enough (misses ball_detections, ball_confidences_2d, references, team_descrs,
shots_post_cv, parts folders). Copy the match's whole `skcr-algo:prod/<MATCH_NAME>/` minus
`edges_parts/` (~1.6 GB) with `s3-copy no-preset --skcr-keys` built from a prod listing. Match folder
names (no id in them) are in earlier SFN failure causes. Test match 2089823 is not in the dev DB.

## Lessons

- Prerelease pins: uv won't lock `X.Y.Za0+user` under a plain `>=X.Y.Z` spec. Pin `>=X.Y.Za0` while
  locking, then restore the plain spec in pyproject and in the lock's `specifier` text. A lib prerelease
  carries its branch's pins, so release it from a commit with `a0` pins (skcr-utils 2.30.1a0 and son
  0.100.1a1 were built with plain pins and could not be locked beside the models prerelease without
  a temporary `override-dependencies`).
- Pin exact versions with `uv lock --upgrade-package "pkg==<exact>"`; a plain refresh picks other
  people's prereleases (e.g. `son 0.101.0a0+adrienmorgado`, `skcr-models 0.40.0a0`).
- Renumbering a migration after dev already applied it: renaming the `django_migrations` row before
  main's earlier migrations ran gives `InconsistentMigrationHistory`; drop the row and columns instead
  and let the deploy apply them in order.
