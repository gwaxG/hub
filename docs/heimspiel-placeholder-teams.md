# Heimspiel placeholder teams

Heimspiel lists knockout fixtures before teams are known ("Winner Group B"). Such teams carry
`show_team: "no"` in the raw payload.

- data-provider-clients 1.14.0 (MR shared/data-provider-clients!44, replaces closed !42): Heimspiel `Team.is_placeholder`
  property → common `Team.is_placeholder`, set in `_to_common_team` (`get_matches`) and `_build_team`
  (`get_match_details[_with_players]`) and `get_teams`.
- wilson `create_provider_matches_from_ce` (son 0.87.1) skips a match if either team is a placeholder:
  info log only, no operation error, counted in `report.count.placeholder_teams_skipped`.
  The next cron run of the `create_matches_from_heimspiel` lambda creates it once both teams are revealed. MR: wilson!2681.
- Only the per-CE flow skips. Single-match creation (`create_provider_match_from_...` around match_utils.py:589)
  still attempts, and fails on team matching.
- The lambda gets son from the registry, so it needs a relock after the son release.
