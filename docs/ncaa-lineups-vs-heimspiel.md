# NCAA lineups vs Heimspiel evaluation

Read-only wilson command `evaluate_ncaa_lineups` (branch `feat/evaluate-ncaa-lineups`, not meant to be merged;
Notion task 856 "Evaluate lineups from NCAA").

- CEs: ours 1896/1898/1899 ↔ Heimspiel seasons 127352/127457/127181 (hard-coded in the command).
- "Launched" = has starters (`TeamPlayerMatch.start_time == 00:00`) and period instruction events. The real
  launch state lives in the DynamoDB pipeline status, not in the DB.
- Match mapping: `MatchMatching(provider='heimspiel')`, else same Heimspiel teams (`TeamMatching`) on the same UTC day.
- Player mapping: `PlayerMatching(provider='heimspiel')`, else normalized "first last" name in our match roster,
  else `hs-<id>` (unmapped).
- Minutes: ours = period start + `(frame - period start) // (VIDEO_FPS*60)`; Heimspiel = period offset
  (0/45/90/105) + `start_minute` — same convention as wilson's Heimspiel event ingestion.
- Positions: Heimspiel `match_team[].tactical_formation_id` + `tactical[].pos_index` → `skc_position` via
  `heimspiel_formations.csv` (next to the command) gives LCB/RCB etc.; fallback to the coarse shortname (`CD` → CB).
  `position_ok` = exact acronym, `position_group_ok` = `PositionGroup`. NCAA CEs had no tactical data at all
  (2026-10-13, 132 finished matches); dpc common models drop `pos_index`/formation id, so the command reads the raw `get_match`.
- Subs paired by (team, player in, player out), closest minute; per-player in/out minutes give a
  pairing-agnostic check for mass substitutions / re-entries.
- Output: `ncaa_lineups_statistics.csv` (scopes: all, per CE, per gender), `ncaa_lineups_matches.csv`,
  `ncaa_lineups_players.csv`. Root cause (Heimspiel vs operator) stays a manual call on the players file.
