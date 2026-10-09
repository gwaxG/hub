# Hub memory index

Index of the `docs/` file lake — one line per file, grouped by system.
Hand-maintained: whoever adds, renames, or removes a file in `docs/` updates
its line here in the same change. Line format: `- [title](docs/slug.md) — one-line hook`.

## hub

- [hub-graph / hub-mr code graph tools](docs/hub-graph-code-graph-tool.md) — `hub-graph` (whole repo) + `hub-mr` (feature integration vs merge base) over one shared engine; artefacts in `hub/tmp`; the sys.path-root, topological-order and base-comparability traps

## data-provider-clients

- [Heimspiel extra time & penalty shootouts](docs/heimspiel-extra-time-and-penalties.md) — how the Heimspiel client models knockout matches past 90'; two data sources (result periods + events) needed together
- [Heimspiel placeholder teams](docs/heimspiel-placeholder-teams.md) — `show_team: "no"`; `Team.is_placeholder` in list + details paths; CE match creation skips them silently (dpc !44 → 1.14.0, wilson !2681)
- [Heimspiel match incident & coverage](docs/heimspiel-match-incident.md) — `match_incident` ids 3/4/6/7 → common `Match.incident`; `is_finished_with_coverage` = finished+full coverage (dpc !43)

## football-metadata-service

- [kubectl guide](docs/football-metadata-service-kubectl.html) — operational kubectl commands for the football-metadata-service cluster

## wilson
- [Match uniqueness window](docs/match-uniqueness-window.md) — duplicate guard for Gaffer/Forest/merge_teams: ±24h home/away pair (was 12h), wilson !2695

- [son schema changes vs football lambdas](docs/son-schema-changes-break-football-lambdas.md) — dropping a son column breaks football + wilson lambdas on older son (they SELECT every declared column); who loads Player, pirlo prerelease relock flow, rollout order
- [Football launch cron + processing pool](docs/football-launch-cron-processing-pool.md) — `_by_cron` = 1-match/min task_by_row over MatchBeating active flag; who sets it; future-match guard (wilson !2664, football !1575)
- [Wilson metadata inventory](docs/wilson-metadata-inventory.md) — what counts as metadata in wilson (descriptive domain entities + operational/internal), what clients consume, and the bounded context for the FMS migration
- [No video on S3 on dev](docs/no-video-on-s3-on-dev.md) — dev pipeline check falls back to legacy skcr-algo-dev mp4 when the vidic-v2 Video row wasn't copied
