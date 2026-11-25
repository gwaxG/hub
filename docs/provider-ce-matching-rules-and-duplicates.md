---
repo: [wilson, data-provider-clients]
mr: [wilson!2860, wilson!2875, wilson!2951, wilson!2814]
verified_at: 2026-11-25
source: https://app.notion.com/p/40e6552a98c98032b916f01f658f58b0
---

# Provider CE matching rules and duplicate matches (task 4110)

State of Notion task 4110 "Prevent duplicate matches: restrict provider CE mapping and clarify match creation
scope", read against wilson `origin/main` at `6582579d0` (2026-11-25). Code was read, no test was run. Paths are
relative to wilson `server/`. Project page: "Rework competition & competition edition mapping with providers".

## MR map of the project

- wilson !2860 (merged 2026-11-24, task 4148): 1 SkillCorner competition → N provider competitions. See
  [competition matching 1-to-N](competition-matching-mapping.md).
- wilson !2875 (merged 2026-11-25, task 4107): 1 SkillCorner CE → N provider CEs. See
  [Heimspiel split seasons](heimspiel-split-seasons-ce-mapping.md). The merged migration is
  `0292_competitioneditionmatching_one_to_many` (0290 is now the unique `(competition, season)` on CE).
- wilson !2951 (open, task 4149): N SkillCorner competitions → 1 provider competition. Unique becomes
  `(competition, provider, provider_competition_id)`. `CompetitionEditionSelector` picks the CE: a
  `ProviderMatchCompetitionEditionOverride` row wins, else the single CE whose `start_date`/`end_date` holds the
  match date, else the match is skipped.
- wilson !2814 + gaffer-front !252 (open): Gaffer match creation from a provider. It reuses
  `REQUIRED_MATCHING_LEVELS_BY_PROVIDER` (Heimspiel = competition + CE).

## How a provider match gets its SkillCorner CE

- `create_provider_match` does not receive the CE that started the run. `Match.provider.get_skillcorner_ce`
  (`son/models/match_provider_manager.py`) resolves it from the provider match:
  1. `provider_match.competition_edition` → `CompetitionEditionMatching` (SmrtStats).
  2. Heimspiel: the season id is tried as a CE matching id.
  3. Fallback for every provider: `CompetitionMatching` + `SeasonMatching` → `CompetitionEdition(competition, season)`.
- The match creation status and `MatchMatching` are keyed by provider match id. So one provider match id cannot
  create 2 matches, whatever CE triggers the run. Duplicates need 2 provider ids for one game, and then
  [the uniqueness window](match-uniqueness-window.md) is the only guard.
- Client behaviour (data-provider-clients): SICS ignores the CE id; SmrtStats requires it and ignores competition
  and season; Heimspiel fetches by season (= CE id) and then **filters by `competition_id`** when one is given. With
  no season it fetches the current matchday of the competition.

## Acceptance criteria against main

- Provider CE on a second SkillCorner CE is blocked: done. DB unique `(provider, provider_competition_edition_id)`,
  Gaffer 409 `competition_edition_matching_already_exists`. The message does not name the owning CE.
- SICS creates matches of all mapped competitions: done by !2860.
- Heimspiel driven by CE matching only: **not met**. `create_provider_matches_from_ce`
  (`son/clients/provider/match_utils.py`):
  - returns `MissingCompetitionMatching` when the competition has no Heimspiel matching;
  - fetches every `(CE id, competition id)` pair, so a mapped Heimspiel CE under an unmapped Heimspiel competition
    gives 0 matches (the client filter drops them);
  - with no CE matching the id list is `[None]`: the fetch goes by competition, and step 3 above resolves the CE.
    The Forest activation refuses Heimspiel auto creation without a CE matching, so only manual invokes reach this.

## Open conflict

!2951 feeds N SkillCorner CEs from one Heimspiel season (NCAA regular season + playoffs) with no CE matching, through
competition matching + dates. Task 4110 says Heimspiel uses CE matching only and one provider CE maps one SkillCorner
CE. The PM must decide: NCAA as a written exception, or no Heimspiel path in !2951.

## Proposed change for 4110 (not started)

Heimspiel only: fetch by CE ids without the competition filter, no competition fallback in `get_skillcorner_ce` and
the single-match path, `MissingCompetitionEditionMatching` when a CE has no matching, drop the competition level from
the Heimspiel entry of `REQUIRED_MATCHING_LEVELS_BY_PROVIDER` (touches !2814).
