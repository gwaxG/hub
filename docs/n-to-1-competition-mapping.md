---
repo: [wilson, data-provider-clients]
mr: [wilson!2951, wilson!2875, wilson!2860]
verified_at: 2026-11-27
source: https://app.notion.com/p/4106552a98c9804780f2d7c484ada31e
---

# N-to-1 competition mapping (Notion 4149): what the problem really is

N SkillCorner competitions matched to one provider competition (NCAA regular season + playoffs). wilson!2951 went through four designs and ended as a ~40-line change; the MR was **closed, not merged** (2026-11-27, head `a28de9ec9`, branch `feat/n-to-1-competition-mapping`). Read this before reopening the topic.

## Tickets (project "Rework competition & competition edition mapping with providers")

- [4148](https://app.notion.com/p/4106552a98c9800bbce4cf901101eb1e) 1-to-N competitions — done, wilson!2860.
- [4107](https://app.notion.com/p/40e6552a98c980e9a142f7c19198e766) 1-to-N competition editions — done, wilson!2875.
- [4149](https://app.notion.com/p/4106552a98c9804780f2d7c484ada31e) N-to-1 competitions — wilson!2951. The text says it applies **only to providers with no CE concept**; how to pick the competition of a match is an open question in the ticket.
- [4110](https://app.notion.com/p/40e6552a98c98032b916f01f658f58b0) guard — one provider CE matches one SkillCorner CE; the project page repeats it as "Constraint to keep".

## How each provider resolves the SkillCorner CE

| Provider | CE concept | Lookup |
|---|---|---|
| Heimspiel | yes, its "season id" is a CE id | `CompetitionEditionMatching` |
| SmrtStats | yes, its "season" is a CE (`smrtstats/client.py`, `get_matches` needs the CE id) | `CompetitionEditionMatching` |
| SICS | no, ignores the CE id | `CompetitionMatching` + `SeasonMatching` |
| Wyscout (old sync) | `seasonId` | `CompetitionEditionMatching.get()`, 1-to-1 |

So 4149 as written only concerns SICS. Resolver: `MatchProviderManager.get_skillcorner_ce` (`son/models/match_provider_manager.py`); creation by provider match id repeats the lookups in `create_provider_match_from_id` (`son/clients/provider/match_utils.py`) to return one error per missing matching.

## Heimspiel NCAA layout (checked through the dpc client, 2026-11-26)

- One Heimspiel competition per conference, with **two CEs**: regular season and playoffs. Example NCAA (D1) Big Ten men, competition 21125: CE 127190 "2026" (has tables) and CE 127250 "2026 Playoff" (1. Round, Semi-finals, Final).
- Old competition 5465 "NCAA": same pattern ("2025" / "2025 Playoffs", "2026" / "2026 Playoffs").
- "NCAA (D1) College Cup" (21101 men, 21176 women) is a separate competition.
- Checked 3 of ~60 NCAA competitions. `raw_competition_list()` + `raw_seasons_by_competition(id)` + `raw_matches_by_season(id)` answer it in three calls.

Consequence: each SkillCorner CE matches its own Heimspiel CE (1-to-1). Only the competition level is N-to-1, and Heimspiel never reads the competition matching to place a match. No shared provider CE, no date rule.

## Why duplicates are not the real risk

A provider match has one `MatchMatching`; the second CE that fetches it finds the existing match. For a provider without CE the real effect of N-to-1 is "which competition gets all the matches", not duplicated matches.

## What actually breaks with N competitions on one provider competition

Reverse lookups `CompetitionMatching.objects.get(provider=..., provider_competition_id=...)` raise `MultipleObjectsReturned`:

- `get_skillcorner_ce`, competition + season path;
- `create_provider_match_from_id`, competition path;
- the gender lookup in the lineup check of `match_provider_manager.py` (read it from the match's own competition instead).

Final design of the MR: constraint `CompetitionMatching` unique on (competition, provider, provider_competition_id), `.filter(...).earliest('id')` in the two lookups (earliest mapping wins, as the scalar readers already do), gender from the match. For SICS that means every match goes to the first matched competition: no duplicate, no crash, no split. Product question (how to pick the competition for a provider without CE) was drafted, not answered.

## Designs tried and dropped

1. `SeasonMatching` holding the Heimspiel CE id of a "shared" edition + a separate metadata cron path — repurposes the table, one shared competition per season (review, Marthe).
2. Shared provider CE: `CompetitionEditionMatching` unique per (CE, provider, provider CE id) + date range on `CompetitionEdition` + `ProviderMatchCompetitionEditionOverride` + a `CompetitionEditionSelector`. Contradicts 4110 and the project constraint, and Heimspiel does not need it.
3. Same without the shared CE, dates/override kept for SICS — no real SICS case, speculative.

Lessons: read the provider's real data before designing (three API calls removed two designs); check the sibling tickets for constraints before relaxing one; a CE-level change for a competition-level ticket is a scope alarm.

## Practical traps met on the way

- main gained a migration with the same number twice during the MR (0292, then 0293): renumber and fix `dependencies`; a custom stack that already applied the old number needs destroy + recreate.
- `server/tests/test_admin.py::test_sidebar_lists_every_registered_model`: a model registered in Django admin also needs an entry in `settings.UNFOLD['SIDEBAR']['navigation']` (`wilson/settings_base.py`).
- son `pyproject.toml`/`uv.lock` conflict on every main bump: take main's `server/uv.lock`, keep our version, `uv lock` in `server/`.

Related: [Heimspiel split seasons & 1-to-N CE mapping](heimspiel-split-seasons-ce-mapping.md), [Match creation workflow](match-creation-workflow.md), [Wilson custom-stack lambda builds](wilson-custom-stack-lambda-builds.md).
