---
repo: [wilson, data-provider-clients]
mr: [wilson!2540]
verified_at: 2026-11-03
---

# Match Creation Workflow

## Overview

Matches are created automatically from external data providers (SICS, SmrtStats, Heimspiel) via a Lambda-based pipeline. The workflow spans three layers: Forest Admin UI for activation, a task-by-row scheduler for orchestration, and provider clients for data fetching.

---

## Data Provider Clients

Both SICS and SmrtStats implement a shared `ProviderClient` protocol (`data-provider-clients` package) with a common data flow:

```
get_competitions() -> list of competitions with embedded seasons
        |
get_matches(season_id, competition_id) -> list of matches for a CE
        |
get_match_details_with_players(match_id) -> events, lineups, videos
```

### Provider Differences

|                    | SICS                                         | SmrtStats                          |
|--------------------|----------------------------------------------|------------------------------------|
| Auth               | Dual credentials (events / no-events) via `SicsClientRouter` | Token-based API key |
| Video timing       | Milliseconds (raw)                           | Seconds (native)                   |
| Position mapping   | `module` + `module_position`                 | Position name string               |
| Match details      | Separate endpoints per data type             | All in `/advanced/videos/`         |
| Player roster      | Separate `/s02.json` endpoint                | Embedded in match details          |
| Caching            | None                                         | Global player/team/competition caches |

### Key Files

- `data-provider-clients/src/data_provider_clients/football/protocol/data_provider_protocol.py` - Common interface
- `data-provider-clients/src/data_provider_clients/football/sics/client.py` - SICS client
- `data-provider-clients/src/data_provider_clients/football/smrtstats/client.py` - SmrtStats client
- `data-provider-clients/src/data_provider_clients/football/sics/router.py` - Dual-auth routing for SICS
- `data-provider-clients/src/data_provider_clients/football/registry.py` - `DataProviderClientRegistry` singleton access

---

## Competition Edition Auto-Creation

### 1. Activation (Forest Admin UI)

An admin selects a `CompetitionEditionBeating` record and clicks "Activate auto creation from a provider".

- Picks a provider from `DataProviderAvailableForAutoCreation` (SICS, SMRT_STATS, HEIMSPIEL)
- Sets `create_matches_from_provider_for_competition_edition_active = True`
- Creates or updates a `MatchCompetitionEditionCreation` record linking the CE to the chosen provider
- Validation: cannot have both Wyscout and provider auto-creation active simultaneously

**Files:**
- `server/api/forest/competition_edition_beating.py` - Activation action handler
- `server/api/forest/competition_edition.py` - Manual launch action
- `server/son/models/match_competition_edition_creation.py` - Provider config model

### 2. Scheduled Execution (Lambda + task-by-row)

A Lambda function (`wilson-create_matches_from_provider_for_c-{ENV}`; Heimspiel: `wilson-create_matches_from_heimspiel_for_-{ENV}`) runs every few minutes via EventBridge (prod/teamapp only — `ENABLE_EVENT_BRIDGE` in `pulumi/02_compute/wilson.py`).

The `@task_by_row_v2` decorator:
- Picks the `CompetitionEdition` with the oldest `last_try` (nulls first) where `active = True`, or exactly the one given as `{"competitionedition_id": id}` in the event
- Respects a **3-hour retry delay** between attempts
- Enforces a **30-minute timeout** per execution
- Tracks `started_at` and `last_try` on `CompetitionEditionBeating`

**Files:**
- `pulumi/aws/third_party_provider/create_matches_from_provider_for_competition_edition/app.py` - Lambda handler
- `server/son/models/task_by_row.py` - task-by-row decorator (lines 155-301)
- `server/son/models/competition_edition.py` - Beating model with task references

### 3. Resolve Provider IDs

Before fetching, the system translates SkillCorner IDs to provider IDs:

- `CompetitionMatching` -> `provider_competition_id`
- `SeasonMatching` -> `provider_season_id`
- `CompetitionEditionMatching` -> `provider_competition_edition_id` (optional)

SmrtStats fetches by `provider_competition_edition_id` only (its "season" is a SKCR CE); `SeasonMatching` + `CompetitionMatching` must still exist or the run aborts before fetching. SICS uses competition + season.

### 4. Fetch and Iterate

Calls `provider_client.get_matches()` to retrieve all matches for the CE from the external provider, then processes each one individually.

**File:** `server/son/clients/provider/match_utils.py` - `create_provider_matches_from_ce()`

---

## Single Match Creation Flow

Handled by `MatchProviderManager.create()` in `server/son/models/match_provider_manager.py`.

### Steps

```
1. get_or_create_mcs()           -> MatchCreationStatus record
2. check_team_matching()          -> Validate home/away teams exist in TeamMatching
3. search_and_match()             -> Search if match already exists in DB
   |-- MATCHED/FOUND              -> Skip or complete missing steps only
   |-- NOT_FOUND                  -> create_missing() -> new Match + MatchMatching
   |-- Error                      -> Log specific error type
4. download_video()               -> Download match footage
5. create_period_events()         -> Create game period records
6. create_lineups()               -> Import player lineups (via get_match_details_with_players)
7. create_match_events()          -> Import match events (goals, cards, subs, etc.)
```

### Status Tracking

Each step tracks progress on `MatchCreationStatus` (one row per provider + provider match id; no FK to Match — join through `MatchMatching`) across 6 dimensions:

| Dimension              | Description              |
|------------------------|--------------------------|
| `status_match`         | Match record creation    |
| `status_lineup`        | Player lineup import     |
| `status_lineup_events` | Match events import      |
| `status_video`         | Video download           |
| `status_period_events` | Game period creation     |
| `status_vidic_events`  | Periods + instructions pushed to the Vidic video |

Values: `to_create`, `done`, `error`, `ignored`, `not_available` (`son/models/match_creation_status.py`).
`ignored` usually means another provider/operator owns that data; lineup steps carry a reason in
`error_lineup.error_details.reason` (`existing_lineup_kept`, `own_lineup_kept`) since wilson !2540.
`not_available` = the provider can't supply it (Heimspiel has no video/periods).

If a match was partially created before, only the missing steps run on the next attempt: an
existing match is re-visited only while `MatchCompletion.is_fully_created` is False
(`son/match_completion.py`), and protected matches (`Match.is_match_protected_from_overwrite`:
post-match, home-team-side check, preprod done) are skipped with MCS `ignored`.

---

## Several providers on one match (Heimspiel + video provider)

- `PROVIDERS_WITH_VIDEO = {SICS, SMRT_STATS}` supply video + periods; `METADATA_ONLY_PROVIDERS =
  {HEIMSPIEL}` supplies match info, and optionally lineups + subs/red cards. Each provider has its
  own CE cron lambda and its own MCS row for the same match.
- Heimspiel can create the match (`create_matches_from_heimspiel_active`); the video provider then
  finds it (search MATCHED/FOUND) and fills video + periods.
- Lineups/instructions come from exactly one source per match, chosen per CE by
  `create_lineups_from_heimspiel` and then frozen by `data_collection.lineup_provider` — details in
  [heimspiel-lineups-wilson-flow](heimspiel-lineups-wilson-flow.md).
- Operator edits (Gaffer/Forest) set `lineup_provider`/`period_frame_provider = 'skillcorner'`;
  `TeamPlayerMatch` writes on a `skillcorner` lineup raise `ProtectedLineupException` unless
  `overwrite_manual_data=True`.
- Last step of each pass: `push_events_to_vidic` (video provider only; Heimspiel just flags
  `status_vidic_events = to_create`).
- Testing on dev (crons off, manual invoke with `competitionedition_id`, dev writes prod Vidic):
  [match-creation-dev-validation](match-creation-dev-validation.md).

### Error Types

When search or matching fails, specific errors are logged:

- `MissingTeamMatching`
- `MissingCompetitionMatching`
- `MissingSeasonMatching`
- `MissingCompetitionEditionMatching`
- `FailedToGetMatchDetailsWithPlayers`

### Reporting

After processing all matches for a CE, a `ProviderMatchCreationReport` is saved to S3 as compressed JSON containing:

- Counts: processed, failed (by error type), incomplete
- Search status distribution: MATCHED / FOUND / MAYBE / NOT_FOUND
- Action taken distribution: NO_ACTION / CREATED / COMPLETED
- Per-match details
- Timeout and dryrun flags

**File:** `server/son/models/provider_match_creation_report.py`

---

## Manual Trigger

Forest Admin also exposes a "Launch provider match creation" action on `CompetitionEdition` records, which invokes the same Lambda directly with a specific CE ID and an optional `dryrun` flag.

**File:** `server/api/forest/competition_edition.py` (lines 379-394)
