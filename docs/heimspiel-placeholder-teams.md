# Heimspiel placeholder teams

Heimspiel lists knockout fixtures before teams are known ("Winner Group B"). Such teams carry
`show_team: "no"` in the raw payload.

- data-provider-clients 1.13.0 maps it to common `Team.is_placeholder` (`_to_common_team`). MR: shared/data-provider-clients!42.
- wilson `create_provider_matches_from_ce` (son 0.87.0) skips a match if either team is a placeholder:
  info log only, no operation error, counted in `report.count.placeholder_teams_skipped`.
  The next cron run of the `create_matches_from_heimspiel` lambda creates it once both teams are revealed. MR: wilson!2681.
- Only the per-CE flow skips. Single-match creation (`create_provider_match_from_...` around match_utils.py:589)
  still attempts, and fails on team matching.
- The lambda gets son from the registry, so it needs a relock after the son release.
