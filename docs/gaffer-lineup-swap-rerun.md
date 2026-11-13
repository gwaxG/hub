---
repo: [wilson]
mr: [wilson!2829]
verified_at: 2026-11-05
source: https://skillcorner.slack.com/archives/C04GQ2WFH6V/p1793813798830259
---

# Gaffer lineup player swap → rerun flag

- A Gaffer match-form save (`MatchUpdateSerializer.update` → `sync_match_lineup`) that replaces a player
  **deletes** the old `TeamPlayerMatch` (and that player's events) and **creates** a new one. Delivered
  data (match_data, DE CSVs, Wyscout events) keeps the old player id until the pipeline reruns.
- Before wilson !2829 nothing flagged, relaunched or warned. Incident 2026-11-03: 1023973 → 531597 on
  2049183 and 2044041, both never relaunched.
- !2829: `sync_match_lineup` returns whether the team_player set changed; if so,
  `gaffer/services/lineup_change_rerun.py` calls `mark_matches_to_rerun` (skips BLANK/NOT_AVAILABLE)
  and adds warning `lineup_changed_match_to_rerun`. No auto-relaunch. The flag is written after
  `data_collection.save()` in `update`, otherwise that save would overwrite it.
- Nothing consumes `TO_RERUN` automatically: it only marks the match. Relaunching stays manual (Gaffer
  launch, or `relaunch_matches`), like the stadium-dimension flow (which is opt-in via `is_relaunching_matches`).
- Same MR also folds in the former wilson !2830: `Match._launch_football_pipeline_lambda` resets
  `dynamic_events_v2_check`/`v3_check` to `None` once the lambda accepts a full run. Reason: after a swap +
  relaunch the Wyscout sync can fail (`WyscoutPlayerIdException`, 2035091), GI v3 takes "Core Events
  Skipped", and the old `True` flags kept the DE API serving stale data. son 0.94.1.
- Scope is wider than DE: tracking (player ids via match_data), physical (S3 files per player) and all GI
  outputs stay on the old player until a rerun.
- Forest has the same gap (verified on wilson main 2026-11-05): `api/forest/teamplayermatch.py` "Force delete
  players from lineup" / "Edit lineup player" and `api/forest/match.py` `add_player_to_team_lineup` only set
  `lineup_provider='skillcorner'`, no flag/relaunch. Forest refuses deleting a TPM with physical rows
  (ProtectedError) and does not delete the player's events; Gaffer does.
- Detection today (per Slack, unverified): Metabase question 6660 "check players not in tracking" lists
  matches whose lineup changed after tracking/physical were generated; refreshed daily, Mohamed Rahmouni +
  Adam route new cases to operators, who relaunch. Readiness also visible on the Grafana
  `wilson-data-readiness-serving` probe.
- Causes split (per Slack): manual operator edits without relaunch (Gaffer/Forest), and automatic lineup
  changes that don't relaunch (BO team investigating, thread in C06MXSVUB2N).
- Product/data agreement (Louis, Mohamed, Marthe, 2026-11-05): flagging a match to rerun on lineup change makes
  sense (inform ops lead Aaron Danino first); the general fix is the still-unowned "global relaunch" topic.
  Any automatic relaunch must guard against relaunch loops (e.g. cap relaunches of one match per 24h).
