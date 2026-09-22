# son schema changes vs football lambdas

Dropping (or renaming) a column on a son model is a cross-repo change: every
son consumer that loads that model on an **older** son still declares the
field, and Django `SELECT`s every concrete column, so the query fails with
`column api_<table>.<field> does not exist` as soon as the wilson migration
runs.

## Who loads `Player` in football

The `dynamic_events_agg` lambdas (`aggregate_pa`, `aggregate_pa_epv`,
`aggregate_pp`, `aggregate_pp_epv`, `aggregate_obe`, `aggregate_obr`,
`aggregate_po`) do

```python
PlayerTotalPlayingTime.objects.filter(...).prefetch_related('team_player_match__team_player')
... .team_player_match.team_player.player.id
```

The prefetch stops at `team_player`, so `.player.id` lazy-loads the full
`Player` row. As of 2026-09-14 all football lambdas are locked on son
`0.70.0` (`pulumi/aws/**/uv.lock`), i.e. well behind wilson's `server/pyproject.toml`.

## Who loads `Player` in wilson's own lambdas

`pulumi/aws/management/aggregate_oop_metrics` (called synchronously by the
production out-of-possession metrics endpoint) does
`TeamPlayerMatch.objects...select_related('team_player__player')`. It installs
son from the index like the football lambdas (locked 0.72.3 on 2026-09-15),
so it needs the same relock as football. It is the only wilson lambda that
loads `Player`; the other 16 son-pinned lambdas only touch Match/Video/etc.

## Getting a son that matches the branch before merging

`uvx pirlo release --project-name wilson --branch <branch>` (needs
`UV_DEFAULT_INDEX` + `AWS_PROFILE`) triggers `package:son` with
`PIRLO_RELEASE` and publishes `<version>a0+<gitlab-username>` (e.g.
`0.75.0a0+andreimitriakov`). Consumers then use spec `son>=0.75.0a0,<1` and
`poe lock_all -u son` (football: `--prerelease=if-necessary-or-explicit`, so
the `a0` in the spec is what lets the prerelease in). The same spec accepts
the final `0.75.0`, so the follow-up is just another `lock_all -u son`.

Gotcha: son 0.75 requires `data-provider-clients>=1.10.1`; a lambda pinning
`data-provider-clients~=1.9.0` (football `provider_events_and_formations`)
cannot take the new son without a dpc bump.

Gotcha 2: this applies to any wilson lambda importing *new son code*, not
only schema changes. `Dockerfile.lambda` does `uv sync --frozen` from the
lambda's own `uv.lock`, so a lambda whose `uv.lock` points at a registry son
older than the branch ships without the new symbols and ImportErrors at cold
start. wilson !2625 hit it: `apply_domain_events` imported `Target` (son
0.75.0) while its lock was repinned to registry son 0.74.0 before the release,
which would have dead-lettered every domain event. Keep the prerelease lock
until the final son is published, then relock.

## Rollout order for a column drop

1. Wilson MR 1: stop reading/writing the field, keep the column (pre-deploy
   ECS tasks still select it). Example: wilson `e352324b2`.
2. Wilson MR 2: `RemoveField` migration + drop from the model + son minor bump.
   Example: wilson MR !2623 (son 0.74.0 -> 0.75.0, `Player.weight`). Include
   the relock of any wilson lambda that loads the model (pirlo prerelease).
3. Football MR relocking the affected lambdas on the prerelease, merged and
   deployed first. Example: football MR !1552.
4. Merge MR 2 (publishes son final, deploys wilson lambdas), then run the
   wilson prod migration. Follow-up: relock everything on the final son.

Grep football for `\.player\b|select_related\(.*player|Player\.objects` (not
just the field name) to find indirect loaders; the field name itself may not
appear anywhere.

## Validating on a personal football stack (done 2026-09-21 for the weight drop)

1. `uvx pirlo deploy --project-name football --branch <branch> --env other --stack-name andrei`
   builds every lambda and deploys the `andrei` stack (~10 min).
2. `uvx --python 3.12 francli football run --match-ids ... --env andrei` publishes the
   matches to SNS; `francli football status --env andrei --match-ids ... --format json`
   or `aws stepfunctions list-executions` on `football_main-andrei` to follow. A full
   run takes ~1h45 per match; the son-dependent lambdas (playing time, aggregate_*)
   run in the last stage, "Tracking Physical and Game Intelligence".
3. A failed `football_main` execution can be resumed with
   `aws stepfunctions redrive-execution` instead of relaunching the whole match.

Gotchas: `uvx francli` picks free-threaded Python 3.14 where orjson does not build,
so pass `--python 3.12`; francli and pirlo need `UV_DEFAULT_INDEX` (private index)
and AWS creds. A stale static entry in `~/.aws/credentials` shadows the `granted`
credential_process in `~/.aws/config`; after SSO expiry, `assume <profile>` (or
delete the static entry and `granted sso login`) is needed.

Result for `Player.weight`: matches 2084142, 2083795, 2083779 SUCCEEDED on son
0.75.0a1 with the column still present (the pre-migration state).
