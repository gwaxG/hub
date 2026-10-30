---
repo: [maldini]
mr: []
verified_at: 2026-10-16
---

# maldini-api: OBR "type + phase" export timeouts (Oct 2026)

WQT off-ball-runs export (`/metrics/game_intelligence/in_possession/off_ball_runs`, `metrics_nocube.py`)
times out when the client picks both variants `obr_type` + `phase`.

- Selected metric columns (casillas `off_ball_runs_serving_metrics/v1_0/metrics_info.py`):
  none 45, obr_type 275, phase 252, **both 2,552** → ~10x wider SELECT of `sum(...)` / p30 aggregates.
- Query runs with `FINAL` (`deduplicate_query`) and, when paginated, a second `SELECT COUNT(*) FROM (<same query>)`
  (`get_total_count_query`), each with its own `max_execution_time`.
- Timeout: `ClickhouseSettings.MAX_EXECUTION_TIME_SEC` / `SEND_RECEIVE_TIMEOUT_SEC`, 25s → 45s in `9b204f7` (2026-10-14); not enough.
- Fix ideas: cheaper count query (count over GROUP BY keys only), pre-aggregated table / projection per variant, or cap variant combos.
