# Physical v3 → ClickHouse: ingestion and serving

Snapshot 2026-10-21. Wilson `origin/main` c8b68fa26, icebergkamp `main` 76a69d8, wemby branch
`init-migration-scipt-bis` 710f050 (unmerged — deployed ClickHouse revision unverified).

## Serving (wilson 6476f9e94, "serve /api/physical/ from ClickHouse, scoped by the ClickPipe tables")

- `get_physical` → `construct_physical_clickhouse_results` only; Redshift read path, shadow
  (`physical_clickhouse_shadow.py`, `PHYSICAL_CLICKHOUSE_SHADOW_SAMPLE_RATE`), `cursor_pagination.py` deleted.
- Scope resolved **in ClickHouse** via materialized CTEs `matches` → `scope` over ClickPipe replicas
  (`football.api_match`, `api_teamplayermatch`, `api_teamplayer`, … `FINAL`, `_peerdb_is_deleted = 0`),
  instead of Postgres-computed `IN (…)` literal id sets (hundreds of KB).
- Still from Postgres, bounded: guardian grant ids (non-staff only), non-postmatch exclusion list
  (`match_id NOT IN`), nationality holders (only when filtered) + page nationalities.
- Names/metadata for the returned page only. Rate limit = `throwIf` in SQL (code 395 → `ResponseTooLarge`).
- Cursor `base64("o:<offset>")`; mirrorable v3 keyset cursors accepted, else 400.
- Hand-made skip index `api_teamplayermatch.idx_match_id set(1000)` — **dropped by a ClickPipe resync**.
- Reads `football.physical_3_0_{2,3}_new` (`physical_clickhouse_query_builder.py`). Design: wilson
  `openspec/changes/physical-clickhouse-cutover/design.md`.
- Known gap: auth/postmatch from live Postgres vs scope from ~1 min-lagged replica.

## Ingestion

```
football SFN (pulumi/aws/main/physical_v3/step_function_config.yaml)
  Physical v3 EKS job → Physical Check lambda → sns:publish football-domain-events (PhysicalV3ReadyEvent [V3, V3_0_3])
     │ files: s3://skcr-football-data-raw-us-{env}/physical/{physical_agg|physical_check}/{maj}/{min}/csv/{match_id}.csv.gz
     │
     ├─► Wilson: SNS → SQS wilson-domain-events-{env} → lambda apply_domain_events
     │     → DataCollection.physical_v3*_status = csv_ready (son/domain_events_mapping.py)
     │     → save_physical_v3 / save_physical_v3_0_3 ECS (5 min): ORM delete+bulk_create into Redshift
     │       Physical_v0_2 / v0_3; success stays saving_in_progress (backup only, no longer sets saved_to_redshift)
     │
     └─► icebergkamp: S3 Object Created/Modified → EventBridge → SQS (021_compute_football/pipeline_physical.py)
           SFN icebergkamp-football-physical-sfn-{env}, cron hourly, prod only:
             1. claimcheck_trigger drains SQS → manifest {kind:{match_id:[version]}}
             2. Glue incrementals (branch ingest_staging): UPDATE deleted=true on (match_id,version) scope,
                INSERT fresh rows, fast-forward main  (common/ingest_common.py)
             3. ack SQS only if all branches succeed
             4. RefreshClickHouseViews lambda: SYSTEM REFRESH VIEW physical_3_0_3_new_refresh, 60 s,
                physical_3_0_2_new_refresh — fire-and-forget (see system.view_refreshes)
           ClickHouse (wemby app/dbstate): refreshable MV REFRESH EVERY 100 YEAR APPEND (= manual only)
             icebergS3(physical_agg, version 0.2|0.3), updated_at > target max − 30 min, ≤ 3000 matches/refresh,
             LIMIT 1 BY match_id, player_id; joins physical_check, match_infos, api_* FINAL
             → physical_3_0_{2,3}_new  ReplacingMergeTree(updated_at, deleted)
                                       ORDER BY (competition_edition_id, player_id, match_id)

wilson sync_physical_clickhouse_status (ECS, 5 min, prod only, server/phys_clickhouse/status_sync.py):
  saving_in_progress|error_during_save within 7 d, CH max(updated_at) (NOT deleted) > last_modified
  → saved_to_clickhouse + last_modified = now(); error log if still missing 6 h after the event.
```

## PeerDB ClickPipe (metadata CDC)

Not in any repo (icebergkamp, wemby, wilson, devops searched) — presumably configured in the ClickHouse
Cloud console. Replicates `api_match`, `api_teamplayermatch`, `api_teamplayer`, `api_player`, `api_team`,
`api_competition`, `api_competitionedition`, `api_season`, `api_playerrole` into `football`, ~53 s lag.
Not replicated: guardian tables, `api_datacollection`, `api_playerarea`, `api_area`. Lag alert still a TODO.

## Gotchas

- Latency to ClickHouse: up to ~1 h cron + Glue + async refresh (unmeasured).
- Upstream S3 deletions not propagated (only Created/Modified subscribed). Wilson match deletion
  (`son/match_data_deletion.py:92-114`) touches neither Iceberg nor ClickHouse, and deletes Redshift
  rows from `Physical_v0_1` only — not v0_2/v0_3 (likely bug, unverified at runtime).
- Readers must use `FINAL` or `NOT deleted`.
- Legacy `physical_3_0_x` (no `_new`) are fed from a frozen Iceberg table; don't serve from them.
- Bulk backfill: wemby `dbstate` CLI, 2000 matches/batch; the 3000/refresh cap exists because the
  2026-10-12 re-ingest rewrote 171k matches.
- Redshift ingest removal: unmerged wilson branch `chore/physical-data-still-ingested-into-redshift-after-t`.
