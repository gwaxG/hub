---
repo: [football, wilson, paulumi, pirlo]
mr: []
verified_at: 2026-11-24
---
# Football custom stack: where each resource resolves

Verified against the football mirror (`workspace/skillcorner/applications/football/pulumi`; kit path on origin/feat/jersey-colors). A custom stack `mr-<iid>` (or a personal stack) is a full football deployment, but its data goes to dev or to its own copy.

## How the stack name reaches football
- `pirlo deploy --env other --stack-name mr-<iid>` sets `ENV=other` and `PAULUMI_CUSTOM_STACK_NAME`. paulumi swaps the stack name (`devops/paulumi/src/paulumi/paulumi.py` `_handle_other_stack`).
- So `pulumi.get_stack()` is `mr-<iid>`, and football uses it as `ENV` (`01_infra/football_infrastructure.py:124`).
- paulumi `get_env_name` folds any non-standard football stack to `dev` (`devops/paulumi/src/paulumi/helpers/utils.py:217-224`). Football uses that fold to decide "personal".

## Resource routing
| Resource | Custom stack `mr-<iid>` | Where in code |
|---|---|---|
| Data buckets `skcr-data`, `skcr-algo`, `skcr-football-data-raw-us`, `skcr-tmp-standard-us` | `-dev` suffix (dev buckets) | `skillcorner-common/pulumi/football.py:40-55`, default branch |
| Pipeline output bucket `skcr-football-pipeline-output-<stack>` | Own bucket, one per stack | `football_infrastructure.py:62-69, 249-254`; `02_compute/football.py:236-244` |
| Wilson DB | Dev DB, read-only (`WILSON_DB_ENV=dev`, `WILSON_DB_READONLY=1`) | `02_compute/football.py:257-268` |
| SSM and Secrets Manager | `/mr-<iid>/...` prefix, settings copied from `/dev/` at deploy | `02_compute/football.py`, `01_infra/personal_stack_settings.py` |
| Vidic | Dev (`vidic_env` is `prod` only when ENV is `prod`) | `01_infra/role_policies.py:17, 351` |
| Wilson API client | Dev API, dev credentials (`FOOTBALL_SKILLCORNER_ENV`) | `02_compute/football.py:249`; `events_and_possession_v4/auto_events_v4/app.py:109` |
| Domain-events SNS topic `football-domain-events-<stack>` | Own topic, no subscriber in the stack | `01_infra/sns_config.py:33-36` |
| Maldini ingestion queue | Not used: `SKILLCORNER_ENV` not in prod/dev, so aggregates emit a domain event | `dynamic_events_agg/aggregate_pa/app.py:113-127` |

## Consequence: kit colour writes need dev
- `standalone/update_team_kit` (jersey-colors branch) does not write the DB. It publishes `MatchHomeTeamKitCorrected` / `MatchAwayTeamKitCorrected` (`update_team_kit/app.py:53-59`). Wilson's consumer links the kit.
- The event goes to the stack's own SNS topic. On `mr-<iid>` nothing subscribes, so the kit change never reaches the DB.
- So jersey-colour tests on a personal stack cannot reach the DB. Deploying to dev works because dev's topic has Wilson's subscription.
- Not verified: the exact Wilson consumer subscription, and whether destroy cleans up the pipeline-output bucket (buckets are retained across destroy, see `_retain_and_adopt_s3_buckets`).

## Gotchas
- Dev is shared. A deploy to dev replaces dev's stack state for everyone. Check `pirlo status` first.
- Older notes say a custom stack writes the dev S3 buckets. That holds for the data buckets only; pipeline outputs are per stack.

Related: [pirlo-francli-dev-loop.md](pirlo-francli-dev-loop.md), [football-launch-cron-processing-pool.md](football-launch-cron-processing-pool.md).
