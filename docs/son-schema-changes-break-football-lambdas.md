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
