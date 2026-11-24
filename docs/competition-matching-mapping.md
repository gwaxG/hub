---
repo: [wilson]
mr: [wilson!2860]
verified_at: 2026-11-24
---

# Competition matching: 1 SkillCorner competition → N provider competitions

Merged in wilson !2860 (squash `9708534f5`, prod deploy 2026-11-24 13:48Z, Notion task 4148). Paths are relative
to wilson `server/`.

- **Model** (`son/models/competition.py`): `CompetitionMatching` keeps `unique_together (provider,
  provider_competition_id)`. Migration `api/0291_competitionmatching_one_to_many` drops `(competition, provider)`, so
  a competition can map to several ids of one provider (e.g. SICS Apertura + Clausura + Intermedio).
  - Rolling 0291 back fails once a competition has 2 ids of one provider.
- **Fan-out**: `CompetitionMatching.objects.get_provider_competition_ids(competition_id, provider)` returns the list.
  `son/clients/provider/match_utils.py` calls the provider once per id and logs
  `provider_competition_id` as `','.join(ids)`. A comma in that log line is how you see a fan-out in CloudWatch.
  - SICS has no CE concept: SC CE = competition matching + season matching. All SICS phases must share one SICS
    season id (season matching stays 1 per season).
  - Some smrtstats CEs already logged 2 ids before the MR (e.g. CE 1308: 1104,516). Behaviour is unchanged.
- **Scalar readers** return the earliest mapping (`.earliest('id')`): `Competition.get_provider_id`,
  `get_other_provider_id`, `CompetitionEdition.get_wyscout_id_for_competition_edition`. Public `<provider>_id`
  fields on `/competitions` stay scalar.
- **Reads keyed by (provider, provider_competition_id)** are safe with N rows: `son/models/match.py`,
  `match_provider_manager.py`, lineups `get_mapping` / `check_missing`, Gaffer edition validator (`.exists()`).
- **Opta lambda** `create_opta_matching_from_us_soccer` loops over all opta ids.
- **Gaffer back**: `gaffer/serializers/competitions/competition_serializer.py` accepts several ids of one provider and
  rejects only a repeated `(provider, id)` (`_duplicate_matchings_errors`).
- **Not done (follow-ups)**:
  - gaffer-front: the competition modal has `isProviderRepeatable=false`. A 2nd row of the same provider shows
    "Choose provider..." but keeps its value. A save sends all rows back unchanged (verified on dev data, comp 95).
    The UI cannot add a 2nd id yet.
  - Forest: `api/forest/match.py:2784` (refresh events from providers) and `:3126` (launch provider match creation)
    use `CompetitionMatching.objects.get(competition_id=..., provider=...)`. They raise `MultipleObjectsReturned`
    once a competition has 2 ids of that provider.
  - son 0.103.0 release + repin of the 3 provider lambdas (they shipped pinned on `0.103.0a2+andreimitriakov`).
- **How it is enabled**: nothing in prod uses N ids yet. Extra mappings are added through the ORM or Django admin.
- **Post-release**: 14 monitoring ticks (13:48Z–16:54Z) found no regression. Log at
  `~/.cache/skillcorner-dev/competition-1-to-n-mapping/monitor-log.md`. The early Heimspiel slowdown on large CEs was
  attributed to the co-deployed `5896e4359`: `match.unique_name` lazy-loads both teams per match in
  `_update_match_metadata_from_provider`. Run times were back to normal by tick 8.
- Metadata cron `update_matches_metadata` is Heimspiel/CE-only and never reads `CompetitionMatching`. football does
  not reference `CompetitionMatching`.
