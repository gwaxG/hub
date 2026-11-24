---
repo: [wilson, football-metadata-service]
mr: [wilson!2824, wilson!2832]
verified_at: 2026-11-19
---

# Wilson Heimspiel player metadata cron & source stamping

The Heimspiel → player metadata sync lives in **wilson**, not FMS. FMS `python -m app.ingestion`
(prod CronJob `ingest-metadata`, 10:00 Paris; was `ingest-players` before argocd !30) is create-only into its own DB and ignores sources.

- Stamping: `son/models/player_metadata_source.py`. `PlayerMetadataSource` is OneToOne to `Player`
  (`player.metadata_source`), with one source per field. Defaults are first/last name = `skillcorner`
  and height/foot/birthday/nationality = `heimspiel`. Migration `api/0276`. Gaffer edits stamp
  `skillcorner` via `gaffer/core/player_metadata_source_sync.py`.
- Sync: `son/clients/provider/player_metadata_sync.py:update_players_metadata`. It walks the squads of
  Heimspiel-mapped teams and fetches /person **only for already-mapped players**. It never creates
  Heimspiel matchings. Fields stamped `skillcorner` are locked (`_is_locked`). `birthday_manually_set`
  also locks birthday. Names are filled only when empty.
- Mappings (`update_player_matchings`) work from the squad feed. A mapping is locked when
  `source=skillcorner`, or when `manually_set` is set and source is not heimspiel. Otherwise it is
  overwritten. A pair already held by another player is reported as a conflict and skipped.
- Command: `ecs/management/commands/update_players_metadata.py --limit N --apply/--no-apply`.
  Its TODO lists the activation preconditions.
- Cron: `pulumi/aws/management/update_players_metadata/ecs_task_config.yaml`. MR !2832 (merged 2026-11-19)
  enables `event_bridge` `cron(0 9 ? * TUE *)`: Tuesdays 09:00 UTC (10:00 Paris in winter, 11:00 in summer,
  because EventRule is UTC only). Prod rule `wilson-update_players_metadata-prod-*` is ENABLED. The sibling
  `update_matches_metadata` uses `rate(6 hours)` and is the one that raises stadium OperationExceptions.
- Errors: the player sync logs per-player and fetch failures with `logger.warning` (no Sentry event, !2832).
  It raises no OperationException. Only an unexpected crash reaches Sentry, on purpose.
- Manual prod run: `aws ecs run-task --region eu-central-1 --cluster wilson-prod --task-definition
  wilson-update_players_metadata-prod --launch-type FARGATE` with the rule's network config (copy it from
  `aws events list-targets-by-rule`). Override the container `update_players_metadata` command to add
  `--no-apply --limit N` for a dry run.
- Backfill commands (`player_metadata_backfill_sources`, `_backfill_mappings`, `_load_mappings`,
  `_discrepancy_report`) are on unmerged branch `feat/player-metadata-update-scripts`.
- Notion task 3946 ("Activate Cron for metadata players") gates activation on the Reep birthday
  report: 2,640 players and 603 wrong Heimspiel matchings.
- Section I tool: `apply_player_birthday_report <csv> [--apply]` (wilson MR !2824, all in the command module).
  Dry run by default. It fixes wrong Heimspiel matchings (stamped `skillcorner` + `manually_set`), sets birthdays
  per verdict and locks `birthday_source=skillcorner`. Conflicts land in `issues` in the outcome CSV, not in the DB.
  The user runs it themself; the backfill branch is not to be merged.
