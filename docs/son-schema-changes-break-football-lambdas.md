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

## Rollout order for a column drop

1. Wilson MR 1: stop reading/writing the field, keep the column (pre-deploy
   ECS tasks still select it). Example: wilson `e352324b2`.
2. Wilson MR 2: `RemoveField` migration + drop from the model + son minor bump.
   Example: wilson MR !2623 (son 0.74.0 -> 0.75.0, `Player.weight`).
3. Merging MR 2 to main publishes son (`package:son` fires on
   `server/pyproject.toml` change). Re-lock the affected football lambdas on
   the new son and deploy football.
4. Only then run the wilson prod migration.

Grep football for `\.player\b|select_related\(.*player|Player\.objects` (not
just the field name) to find indirect loaders; the field name itself may not
appear anywhere.
