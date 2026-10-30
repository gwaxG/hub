# Hub memory index

Index of the `docs/` file lake — one line per file, grouped by system.
Hand-maintained: whoever adds, renames, or removes a file in `docs/` updates
its line here in the same change. Line format: `- [title](docs/slug.md) — one-line hook`.

## hub

- [maldini-api OBR variant timeout](docs/maldini-api-obr-variant-timeout.md) — obr_type+phase = 2,552 aggregate cols, FINAL + count re-query blow the 45s CH limit
- [hub-graph / hub-mr code graph tools](docs/hub-graph-code-graph-tool.md) — `hub-graph` (whole repo) + `hub-mr` (feature integration vs merge base) over one shared engine; artefacts in `hub/tmp`; the sys.path-root, topological-order and base-comparability traps
- [pirlo + francli dev loop](docs/pirlo-francli-dev-loop.md) — prerelease → pin → deploy (custom stack vs dev/staging) → francli pipeline green → destroy; custom-stack mechanics and DB topology

- [Infra team regular work](docs/infra-team-regular-work.md) — 6-month MR analysis of the 4 infra engineers: IAM tickets ~31%, Cognito, capacity tuning

## data-provider-clients

- [Heimspiel implementation overview](docs/heimspiel-implementation-overview.md) — Heimspiel as secondary metadata provider in wilson (no video): pipeline alongside SICS/SmrtStats (Apr 2026 snapshot)
- [Heimspiel match matchings script](docs/heimspiel-match-matchings.py) — list SkillCorner matches, resolve each one's Heimspiel MatchMatching via `get_match_matching`

- [Heimspiel extra time & penalty shootouts](docs/heimspiel-extra-time-and-penalties.md) — how the Heimspiel client models knockout matches past 90'; two data sources (result periods + events) needed together
- [Heimspiel placeholder teams](docs/heimspiel-placeholder-teams.md) — `show_team: "no"`; `Team.is_placeholder` in list + details paths; CE match creation skips them silently (dpc !44 → 1.14.0, wilson !2681)
- [Heimspiel match incident & coverage](docs/heimspiel-match-incident.md) — `match_incident` ids 3/4/6/7 → common `Match.incident`; `is_finished_with_coverage` = finished+full coverage (dpc !43)
- [Heimspiel lineup & instruction ingestion](docs/heimspiel-lineup-ingestion.md) — task 807: TeamLineup (bench, sub-only players, rebuilt starters), subs+red cards only, minute−1+extra_minute timing (dpc !48 → 1.16.0, wilson !2540)

## football-metadata-service

- [FMS architecture](docs/football-metadata-service-architecture.html) — football-metadata-service architecture page
- [Metadata migration wilson → FMS](docs/metadata-migration-wilson-to-football-metadata-service.html) — migration plan page
- [Multi-sport metadata service architecture](docs/metadata-service-architecture.md) — early proposal: match creation out of wilson into per-sport pipelines (Apr 2026)
- [Multi-sport metadata service final architecture](docs/metadata-service-final-architecture.md) — final proposal: central FastAPI metadata service for state + orchestration (Apr 2026)

- [kubectl guide](docs/football-metadata-service-kubectl.html) — operational kubectl commands for the football-metadata-service cluster

## wilson

- [Match creation workflow](docs/match-creation-workflow.md) — provider match creation: Forest Admin activation → task-by-row scheduler → provider clients
- [Heimspiel vs SICS/SmrtStats in Forest Admin](docs/heimspiel-vs-all.md) — CompetitionEdition match-creation UI compared across providers
- [NCAA lineups vs Heimspiel](docs/ncaa-lineups-vs-heimspiel.md) — read-only `evaluate_ncaa_lineups` command (unmerged branch); mapping, minute and position conventions
- [Match uniqueness window](docs/match-uniqueness-window.md) — duplicate guard for Gaffer/Forest/merge_teams: ±24h home/away pair (was 12h), wilson !2695
- [Prod DB overload 2026-10-15](docs/prod-db-overload-octopol-2026-10-15.md) — gaffer 504s: octopol 6-account deep-offset/huge-filter API scraping OOM-restarted skcr-prod-aurora; how to investigate (PI, Logs Insights, Sentry API); fix wilson !2722

- [son schema changes vs football lambdas](docs/son-schema-changes-break-football-lambdas.md) — dropping a son column breaks football + wilson lambdas on older son (they SELECT every declared column); who loads Player, pirlo prerelease relock flow, rollout order
- [Football launch cron + processing pool](docs/football-launch-cron-processing-pool.md) — `_by_cron` = 1-match/min task_by_row over MatchBeating active flag; who sets it; future-match guard (wilson !2664, football !1575)
- [Find client IP by username](docs/find-client-ip-by-username.md) — no log has user+IP; join CloudWatch `request_log` (user) with CloudFront logs in `skcr-files-prod/cf-logs/` (IP, ~1 week) on time+path+params; WAL calls only show the WAL server IP (34.34.246.x)
- [No video on S3 on dev](docs/no-video-on-s3-on-dev.md) — dev pipeline check falls back to legacy skcr-algo-dev mp4 when the vidic-v2 Video row wasn't copied

## cicd-catalogs
- [cicd-release lint-mr-title runner tags](docs/cicd-release-lint-mr-title-runner-tags.md) — untagged job queued ~17 min on SaaS runners; `lint_tags` input (MR !95)
