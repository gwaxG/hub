---
repo: [wilson]
mr: []
verified_at: 2026-10-12
---

# Forest Admin: Heimspiel vs SICS/SMRTSTATS — Match Creation Comparison

## CompetitionEdition Detail Page

```
  SICS / SMRTSTATS                          HEIMSPIEL
  ──────────────                            ─────────

  Fields shown:                             Fields shown:
  · create_matches_from_provider  (bool)    · create_matches_from_heimspiel  (bool)
  · create_matches_from_provider_last_try   · create_matches_from_heimspiel_last_try

  Actions:                                  Actions:
  · "Launch provider match creation         · "Activate Heimspiel match creation"
     for competition edition"               · "Deactivate Heimspiel match creation"
     └─ Invokes lambda directly,
        one-shot execution
```

## CompetitionEditionBeating Detail Page

```
  SICS / SMRTSTATS                          HEIMSPIEL
  ──────────────                            ─────────

  Action: "Activate auto creation           Action: "Activate auto creation
           from a provider for a CE"                  from Heimspiel"
    │                                         │
    ├─ Form: pick Provider dropdown           ├─ No form (hardcoded)
    │   (SICS | SMRT_STATS | HEIMSPIEL)       │
    ├─ Guard: Wyscout not active?             ├─ Guard: Wyscout not active?
    ├─ Guard: Heimspiel not active?           ├─ Guard: Provider not active?
    │                                         ├─ Guard: CE matched to Heimspiel?
    ├─ Creates MatchCompetitionEdition-       │
    │  Creation(ce, provider)                 ├─ (no extra record needed)
    └─ Sets …_provider_…_active = True        └─ Sets …_heimspiel_active = True

  Action: "Deactivate auto creation           Action: "Deactivate auto creation
           from a provider for a CE"                    from Heimspiel"
```

## CompetitionEditionMatching

```
  SICS / SMRTSTATS                          HEIMSPIEL
  ──────────────                            ─────────

  (no hook)                                 after_create_hook:
                                              └─ If provider == 'heimspiel':
                                                   auto-set beating
                                                   …_heimspiel_active = True
                                                   (no manual activation needed)
```

## Match Detail Page

```
  SICS / SMRTSTATS                          HEIMSPIEL
  ──────────────                            ─────────

  Action: "Create Provider Match"           Action: "Create Provider Match"
    │                                         │  (same action, different path)
    ├─ Form: match_id + CE + provider         ├─ Form: match_id + CE + provider
    │                                         │
    ├─ Resolves:                              ├─ Resolves:
    │   CompetitionMatching → comp_id         │   CompetitionEditionMatching → ce_id
    │   SeasonMatching → season_id            │   SeasonMatching → SKIPPED
    │   CompetitionEditionMatching (opt)       │
    │                                         │
    └─ Invokes lambda with all IDs            └─ Invokes lambda with season_id=None

  Action: "Refresh events from SICS"        (not available for Heimspiel)
    └─ Deletes events, re-fetches
       from SICS API, re-creates
```

## Mutual Exclusion Matrix

```
  Active ↓  \ Trying to activate →   Provider    Heimspiel    Wyscout
  ─────────────────────────────────  ──────────  ──────────  ──────────
  Provider (SICS/SMRT)                  —           ✗            ✗
  Heimspiel                             ✗           —            ✗
  Wyscout                               ✗           ✗            —

  Only ONE auto-creation source allowed per CompetitionEdition.
```

## Activation Flow Summary

### SICS / SMRTSTATS (manual only)

```
  Forest user
    → Beating action "Activate from provider"
      → pick SICS/SMRT_STATS
        → MatchCompetitionEditionCreation created
          → beating flag set
            → lambda picks it up every 3 min
```

### Heimspiel (auto or manual)

```
  Path A — automatic:

    Forest user creates CompetitionEditionMatching(provider=heimspiel)
      → after_create_hook fires
        → beating flag auto-set             ← zero extra clicks
          → lambda picks it up every 3 min

  Path B — manual:

    Forest user
      → CE action "Activate Heimspiel match creation"
        → beating flag set
          → lambda picks it up every 3 min
```

## Match Creation Workflow — End-to-End Pipeline

### SICS / SMRTSTATS

```
  EventBridge (every 3 min)
       │
       ▼
  Lambda: create_matches_from_provider_for_competition_edition
       │
       ▼
  @task_by_row_v2 picks CE where …_provider_…_active = True
       │
       ▼
  create_provider_matches_from_ce(skcr_ce)
       │
       ├─ provider ← MatchCompetitionEditionCreation.provider
       ├─ comp_id  ← CompetitionMatching
       ├─ season_id ← SeasonMatching (or CompetitionEditionMatching)
       │
       ▼
  provider_client.get_matches(competition_id, season_id)
       │                          ↑ returns finished matches only
       ▼
  FOR EACH provider_match:
       │
       ├─ check_team_matching(home + away)
       ├─ get_or_create MatchCreationStatus
       │
       ▼
  Match.provider.create()
       │
       ├─ search_and_match()
       │     ├─ MatchMatching exists?  → MATCHED (skip creation)
       │     ├─ teams + CE + date ±1d? → FOUND
       │     ├─ teams + CE + date ±2d? → MAYBE
       │     └─ nothing?               → NOT_FOUND → create Match + MatchMatching
       │
       └─ Post-creation pipeline (all steps, sequential):
            1. Download video           → status_video
            2. Create period events     → status_period_events
            3. Create lineups           → status_lineup
            4. Create match events      → status_lineup_events
       │
       ▼
  Save report to S3
```

### Heimspiel

```
  EventBridge (every 3 min, retry_delay 3h)
       │
       ▼
  Lambda: create_matches_from_heimspiel_for_competition_edition
       │
       ▼
  @task_by_row_v2 picks CE where …_heimspiel_active = True
       │
       ▼
  create_heimspiel_matches_from_ce(skcr_ce)
       │
       ├─ ce_id ← CompetitionEditionMatching.provider_competition_edition_id
       │           (no CompetitionMatching / SeasonMatching)
       │
       ▼
  provider_client.get_matches(season_id=ce_id)
       │                          ↑ returns ALL matches (played + unplayed)
       ▼
  FOR EACH provider_match:
       │
       ├─ MatchMatching(provider=heimspiel, id=match.id) exists?
       │
       │   YES ──────────────────────────────────────────────────
       │   │
       │   ▼  PATH A: _update_heimspiel_match()
       │      ├─ Compare status  (NOT_STARTED → CLOSED?)
       │      ├─ Compare datetime (fixture rescheduled?)
       │      ├─ Compare scores  (for finished matches)
       │      ├─ Update DB if changed
       │      └─ → EXISTING_MATCH_UPDATED or NO_ACTION
       │
       │   NO ───────────────────────────────────────────────────
       │   │
       │   ├─ finished == False?
       │   │
       │   │  YES ───────────────────────────────────────────────
       │   │  │
       │   │  ▼  PATH B: _create_heimspiel_scheduled_match()
       │   │     ├─ Resolve teams via TeamMatching
       │   │     ├─ Create Match (status=NOT_STARTED)
       │   │     ├─ Create MatchMatching
       │   │     ├─ Create MatchCreationStatus (all NOT_AVAILABLE)
       │   │     └─ NO lineups, NO events, NO video
       │   │
       │   │  NO ────────────────────────────────────────────────
       │   │  │
       │   │  ▼  PATH C: create_provider_match()  ← reuses generic pipeline
       │   │     ├─ check_team_matching()
       │   │     ├─ get_or_create MatchCreationStatus
       │   │     ├─ Match.provider.create()
       │   │     └─ Full pipeline: video + periods + lineups + events
       │   │
       │   ▼
       ├─ _create_cross_provider_matchings()
       │     ├─ Extract Heimspiel's cross-provider IDs:
       │     │     '68' → statsperform    '81' → wyscout
       │     │     '102' → sics           '105' → impect
       │     │     '113' → statsbomb
       │     ├─ Auto-create MatchMatching per provider
       │     └─ Auto-create TeamMatching per provider
       │           (soft-fail: errors logged, never propagate)
       │
       ▼
  Save report to S3
```

### Pipeline Comparison at a Glance

```
                 SICS / SMRTSTATS                 HEIMSPIEL
                 ────────────────                 ─────────
  Lambda         create_matches_from_provider_…   create_matches_from_heimspiel_…
  Trigger        EventBridge 3 min                EventBridge 3 min (retry 3h)
  ID resolution  comp_id + season_id              single ce_id
  API call       get_matches(comp, season)        get_matches(season=ce_id)
  Matches        finished only                    finished + scheduled
  Per-match:
    existing?    skip (MATCHED)                   update status/date/scores
    unplayed?    N/A                              create bare record
    finished?    full pipeline                    full pipeline (reused)
  Post-match     —                                cross-provider matchings
  Report         S3                               S3
```

## Structural Differences

| Aspect | SICS / SMRTSTATS | Heimspiel |
|---|---|---|
| ID resolution | SICS: `comp_id` + `season_id`; SmrtStats: `ce_id` (SmrtStats "season" = SKCR CE; `get_matches` raises without it) | single `ce_id` |
| Matches returned | finished only | finished + scheduled |
| Match creation paths | 1 (full pipeline) | 3 (update / bare / full) |
| Updates existing? | No (immutable) | Yes (status, date, scores) |
| Cross-provider IDs | N/A | Auto-created |
| Activation record | `MatchCompetitionEditionCreation` | None (just beating flag) |
| Prerequisite matchings | `CompetitionMatching` + `SeasonMatching` + `TeamMatching` | `CompetitionEditionMatching` + `TeamMatching` |
