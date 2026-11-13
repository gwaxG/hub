---
repo: [wilson]
mr: [wilson!2782, wilson!2820, wilson!2822]
verified_at: 2026-11-03
---

# wilson data readiness probe + Grafana dashboards

MR wilson!2782 (`feat/grafana-dashboard`). Lambda `pulumi/aws/third_party_provider/data_readiness_probe/`
(prod only, hourly, read-only) + 5 dashboards in `grafana/dashboards/` (Backend Serving, Match Creation,
Gaffer = Athena on ALB logs; Data Readiness Serving / Metadata = Logs Insights on the probe's log group).

## What it checks and when it alerts
One SNS e-mail per module per run when any of its checks is `ko` or `error` (crash, timeout, unreadable body);
every check also logs one JSON line for Grafana.
- Sample: ≤5 recent (postmatch 3–27h ago) + ≤5 modified (played >7d ago, match/teams/players/lineups/
  edition/stadium/sequences `updated_at` in last 24h, 2,000 candidates per change kind). Only `postmatch`.
- match_creation (AWS/Lambda metrics, last 1h): every invocation failed (≥3; ≥9 for on-demand
  `create_match_from_provider`, retries included); scheduled `*_for_competition_edition` not invoked.
- metadata_update: no `update_matches_metadata` log line in 7h.
- pipeline: >3 stuck matches = played 24h–7d ago, `prepare_preprod_for_match_done`, status not
  postmatch/not_available, match not cancelled/postponed. `recent_sample` only logs. `setup` crash skips serving.
- tracking: anything but a 302 to S3 (10s timeout).
- physical: DB status not `saved_to_redshift`/`saved_to_clickhouse` (legacy matches carry redshift); API
  non-200 or empty. Players censored by `physical_check_passed=false` (metrics nulled, identity/minutes kept)
  are logged as `censored_count`, never alerted (data quality, not outage; a whole match can be censored).
- dynamic_events: v3 else v2 per quality check; non-200 (500 + "support has been informed" →
  `error_code=CSVKeyError`), empty, or no answer. Read timeout 30s (endpoint takes 7–18s), connect 10s.
- game_intelligence: only when `dynamic_events_v2_check`; `gi_db` = 5 family timestamps, then 5 aggregated
  endpoints `metrics/game_intelligence/{family}?match={id}` (!2822). The per-match CSV endpoint
  `match/{id}/metrics/game_intelligence/{family}` returns 422 when the file's first player has
  `gi_check_passed=false` even if wilson's v2 check passed; the aggregated ones censor players instead.
- Less than 180s of lambda time left: remaining matches are `error` "not checked", reports still sent.
- Outside prod `api_from_env()` returns an httpx MockTransport failing one check per family.

## Noise tuning after first prod day (!2820, 2026-11-03)
First day: ~38% dynamic events ReadTimeouts at 10s, fully censored physical matches, stuck count
oscillating 3→13 on a weekend at a 6h window. Fixes: 30s read timeout, censored logged only, 24h window.
Next runs were all ok. Real leads left: match 2100122 stuck all day 2026-11-02; GI 422 on 2096891.

## Non-obvious behaviour (from Lucien's review)
- `update_matches_metadata` writes `MetadataUpdateHistory` rows only per eligible match; with no eligible
  match (summer break) it runs and writes nothing. "Ran" is read from its ECS log streams instead:
  group `wilson-<env>`, stream prefix `update_matches_metadata-<env>` (`ecs_utils.py` awslogs prefix).
  `FilterLogEvents` can return an empty page with a `nextToken`: keep paging.
- Async Lambda invokes (EventBridge, backoffice `InvocationType="Event"`) retry twice by default; paulumi
  sets no retry config. One failed on-demand `create_match_from_provider` call = 3 invocations, 3 errors.
- `lambda_config.yaml` key `maximum_retry_attempts` is wired in `pulumi/02_compute/wilson.py`
  (FunctionEventInvokeConfig); the probe sets 0 and stops starting checks 180s before its 600s timeout.

## Alerts and deploy
- SNS `wilson-backend-alerts-<env>` (prod only, `01_infrastructure/backend_alerts.py`) → e-mail to
  #product-area-backend-alerts. Chatbot was dropped: wilson CI role lacks `chatbot:*` / PassRole.
  After first deploy the confirmation e-mail in the channel must be clicked once.
- Dashboards are imported by hand (online Grafana stores v2 schema). Kickoff-template services publish via
  `pulumiverse_grafana` in `pulumi/01_infrastructure/grafana_dashboard_config.py` (token
  `GRAFANA_AUTH_TOKEN`, publish from prod only); a candidate follow-up for wilson.
- Local Grafana: `make monitoring` (127.0.0.1:3000); provisioning files are local-only, same datasource uids.
- Cost estimate: ~$1/month (probe ~$0.35, Athena ~$0.75 at one view of each dashboard per day).
