---
repo: [wilson, son, vidic]
mr: [wilson!2540]
verified_at: 2026-11-03
---

# Heimspiel lineups & instructions in wilson (wilson !2540)

Wilson side of task 807 (dpc side: [heimspiel-lineup-ingestion](heimspiel-lineup-ingestion.md)).
Merged 2026-11-03 as squash `0c54f47c5`, son **0.91.0**, dpc 1.16.3, migration
`api/0281_competitioneditionbeating_create_lineups_from_heimspiel`. Lambdas relocked to 0.91.0
in `736a8a6c3` and deployed to prod the same day.

## Who supplies the lineup (per CE, per match)

- Setting: `CompetitionEditionBeating.create_lineups_from_heimspiel` (default False). Effective
  only with `create_matches_from_heimspiel_active` too
  (`CompetitionEditionBeating.heimspiel_supplies_lineups`).
- `_is_lineup_source(provider, match)` (`son/models/match_provider_manager.py`): lineups +
  instruction events come from Heimspiel **or** the video provider (SICS/SmrtStats), never both.
  Video and periods always come from the video provider.
  - Match with **no lineup rows yet**: Heimspiel if the CE setting is on and the match has a
    Heimspiel `MatchMatching`, else the video provider (an unmatched match is still filled).
  - Match **with rows**: decided by `data_collection.lineup_provider`, not by the CE setting. Once
    created, a lineup keeps its source (Heimspiel, video provider or operators) even if the setting
    changes.
- Non-source provider: `_set_lineup_steps_ignored` → `status_lineup`/`status_lineup_events`
  `ignored`, **no reason**.
- Heimspiel lineup steps only run on finished matches (`provider not in METADATA_ONLY_PROVIDERS or
  provider_match.finished`).

## Kept lineups: `ignored` + reason (`_keeps_existing_lineup`)

The source provider reaches `create_lineups`; an existing lineup is kept when:
- rows were created by someone else (`_has_lineup_from_elsewhere`: `lineup_provider != provider`)
  → `IGNORED`, `error_details.reason = existing_lineup_kept`;
- Heimspiel's own rows exist and the last pass did not skip potential duplicates
  → `IGNORED`, `own_lineup_kept`.

`_lineup_step_status`: SUCCESS→done, IGNORED→ignored, anything else→error.

| Lineup on the match | `lineup_provider` | Heimspiel lineup step | SICS lineup step |
|---|---|---|---|
| Operator edited it (Gaffer/Forest) | `skillcorner` | ignored, no reason | ignored, `existing_lineup_kept` |
| Heimspiel's, untouched, incomplete (e.g. no formation) | `heimspiel` | ignored, `own_lineup_kept` | ignored, no reason |
| SICS's | `sics` | ignored, no reason | done / `own_lineup_kept` |
| None yet | — | Heimspiel creates it | ignored, no reason |

**Operators flip the provider themselves**: Gaffer timeline sync (`_flip_providers` in
`gaffer/serializers/matches/match_timeline_sync.py`), Forest teamplayermatch/events/match actions
and the operator match view set `lineup_provider = 'skillcorner'`. The MR only reads it.

**Before vs after for operator lineups**: before the MR they were already never written —
`TeamPlayerMatch.save/delete/update` call `raise_if_protected` (`son/models/match.py`), which raises
`ProtectedLineupException` on a `skillcorner` lineup without `overwrite_manual_data=True`. SICS's
re-sync of an incomplete operator lineup therefore ended in `error` on every pass (or a silent
`done` when it had nothing to write). Now it is `ignored` + `existing_lineup_kept`. Same data,
cleaner status (prod: "Unexpected error when creating lineups" dropped right after the deploy).

## Instruction events and Vidic

- Heimspiel sends substitutions + red cards only. With Heimspiel as source, the match's
  instructions are all `src_id = heimspiel`; periods stay SICS/SmrtStats.
- **Inline retrieval**: when the video provider places the periods of a match whose lineup is
  Heimspiel's, `retrieve_heimspiel_events` fetches Heimspiel's subs in the same pass (dev: ~2 s after
  the periods) instead of waiting for Heimspiel's next CE pass (`retry_delay` 3 h). Only the
  SICS/SmrtStats periods pass triggers it — periods entered manually wait for Heimspiel's pass.
- `push_events_to_vidic` (last creation step, best-effort, on commit):
  - Heimspiel has no video: when its lineup/events changed it calls
    `set_vidic_events_status(match, TO_CREATE)` on every provider of the match.
  - Video provider pushes when its own periods/lineup/events `changed` (full write) or when
    `status_vidic_events` is to_create/error (`only_if_out_of_sync`). Outcome → `done`/`error`.
  - `push_match_events_to_vidic` sends `provider=video.provider`, so Heimspiel subs show in Vidic
    as `sics`/`smrtstats`. Instruction dicts: substitution `period_index, timestamp, provider,
    team_side, type, jersey_out, jersey_in`; card `…, card_type, jersey, cancelled`.
  - **Known gap**: `_vidic_in_sync` (`son/vidic_instruction_push.py`) compares instruction
    **counts only**, so a same-count Heimspiel correction after creation is not pushed. Product
    tracks post-creation Heimspiel corrections in a separate ticket.
- A push overwrites what Vidic holds. SmrtStats/OBOS prod videos hold operators' Gaffer
  instructions (`provider: skillcorner`) — don't trigger pushes there for testing.

## Completeness (`son/match_completion.py`)

A match is re-visited by the crons only while incomplete (`MatchCompletion.is_fully_created`:
match info, video, periods, lineups, lineup events). Lineup complete = 11 starters per team,
goalkeeper count, no SUB with playing time, unique jersey numbers. Heimspiel without a formation
(OBOS, Botola) → every starter SUB → never complete until an operator sets positions. Protected
matches (`is_match_protected_from_overwrite`: post-match, home-team-side check, preprod done) are
skipped with MCS `ignored`.

## Prod rollout gotchas

- `AddField(BooleanField(default=False))` without `db_default` → column `NOT NULL` with no DB
  default. A lambda on an **older** son that INSERTs the model fails with `IntegrityError`.
  `task_by_row_v2` `get_or_create`s the beating row, and CEs without one are picked first
  (`last_try` nulls first) — so every `Model=CompetitionEdition` lambda must be relocked
  (heimspiel cron, provider cron, `create_opta_matching_from_us_soccer`). See
  [son-schema-changes-break-football-lambdas](son-schema-changes-break-football-lambdas.md).
- Don't merge with the lambdas locked on a personal prerelease (`0.91.0a8+andreimitriakov` went to
  main in the squash; relocked afterwards).
- `deploy_compute` can fail on `sentry:index/getSentryKey ... RST_STREAM` — transient Pulumi Sentry
  provider gRPC reset; retry the job.
- Post-deploy checks (read-only): cron lambda logs (no new error types), MCS lineup statuses,
  `existing_lineup_kept` counts, Vidic = expected payload on a few finished matches.

How it was validated on dev: [match-creation-dev-validation](match-creation-dev-validation.md).
