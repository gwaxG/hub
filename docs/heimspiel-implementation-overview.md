---
repo: [wilson, data-provider-clients]
mr: []
verified_at: 2026-04-24
---

# Heimspiel Integration — Implementation Overview

## Summary

Integrates Heimspiel as a secondary match metadata provider into Wilson. Heimspiel provides fixtures, scores, lineups, events, and cross-provider IDs — but **no video**. It runs as an independent pipeline alongside the existing SICS/SmrtStats providers.

---

## Changed Files Graph

```
wilson/
├── server/
│   ├── son/models/
│   │   ├── match_creation_status.py ─────── + NOT_AVAILABLE status
│   │   │                                    + PROVIDERS_WITH_VIDEO constant (single source of truth)
│   │   │                                    + set_ignored_if_not_actionable preserves NOT_AVAILABLE
│   │   │
│   │   ├── match_provider_manager.py ────── + No-video provider support (skip video/period)
│   │   │                                    + provider field on ProviderMatchCreateReport
│   │   │                                    + EXISTING_MATCH_UPDATED enum
│   │   │                                    + CompetitionEditionMatching fallback in get_skillcorner_ce
│   │   │                                    + get_or_create_mcs accepts str|DataProvider
│   │   │
│   │   ├── competition_edition.py ───────── + Beating task: create_matches_from_heimspiel_for_ce
│   │   │
│   │   └── match.py ─────────────────────── Minor match creation fixes
│   │
│   ├── son/clients/provider/
│   │   ├── match_utils.py ───────────────── MAIN FILE — 5 new functions:
│   │   │   │                                  create_heimspiel_matches_from_ce()
│   │   │   │                                  _create_heimspiel_scheduled_match()
│   │   │   │                                  _update_heimspiel_match()
│   │   │   │                                  _create_cross_provider_matchings()
│   │   │   │                                  _heimspiel_status()
│   │   │   │                                + Unplayed match routing in create_provider_match
│   │   │   │                                + CompetitionEditionMatching fallback for season_id
│   │   │   │                                + str() casting for provider IDs
│   │   │   │
│   │   │   └── uses ──► match_provider_manager.py (create/search/update)
│   │   │        uses ──► match_creation_status.py (PROVIDERS_WITH_VIDEO, MCS states)
│   │   │
│   │   └── __init__.py ──────────────────── + Export create_heimspiel_matches_from_ce
│   │
│   ├── api/forest/
│   │   ├── competition_edition_beating.py ── + HEIMSPIEL in provider dropdown
│   │   │                                     + "Activate auto creation from Heimspiel"
│   │   │                                     + "Deactivate auto creation from Heimspiel"
│   │   │                                     + Mutual exclusion (Wyscout ↔ Provider ↔ Heimspiel)
│   │   │
│   │   └── match.py ─────────────────────── Minor Heimspiel support in match actions
│   │
│   ├── api/management/commands/
│   │   ├── create_match.py ──────────────── NEW — CLI match creation with args
│   │   └── validate_match.py ────────────── NEW — 12-check match readiness validator
│   │
│   ├── api/migrations/
│   │   └── 0251_heimspiel_integration.py ── Beating fields + NOT_AVAILABLE status
│   │
│   └── tests/
│       └── test_data_provider_integration.py ── + 11 Heimspiel tests (3 MCS + 8 CE)
│
├── pulumi/
│   ├── 01_infrastructure/
│   │   └── role_policies.py ─────────────── + HEIMSPIEL_USERNAME (SSM)
│   │                                        + HEIMSPIEL_PASSWORD (Secrets Manager)
│   │
│   └── aws/third_party_provider/
│       ├── create_matches_from_heimspiel_for_competition_edition/  NEW LAMBDA
│       │   ├── app.py ───────────────────── @task_by_row_v2, every 3 min
│       │   ├── lambda_config.yaml ───────── prod, tactical, gi, dev
│       │   └── pyproject.toml
│       │
│       ├── create_match_from_provider/
│       │   └── lambda_config.yaml ───────── + dev environment
│       │
│       └── create_matches_from_provider_for_competition_edition/
│           └── lambda_config.yaml ───────── + dev environment
│
└── cicd/lambda-builds.yml ───────────────── + CI/CD for new Heimspiel Lambda
```

---

## Logic Workflow

### Match Creation Flow (Heimspiel Lambda)

```
EventBridge (every 3 min)
    │
    ▼
Lambda: create_matches_from_heimspiel_for_ce
    │
    ▼
@task_by_row_v2 picks next CE where
    create_matches_from_heimspiel_for_ce_active = True
    │
    ▼
create_heimspiel_matches_from_ce(skcr_ce)
    │
    ├── Resolve Heimspiel CE ID via CompetitionEditionMatching
    │
    ├── get_matches(season_id=provider_ce_id)  ← fetches ALL matches (played + unplayed)
    │
    └── For each match:
            │
            ├── MatchMatching exists? ──YES──► _update_heimspiel_match()
            │                                   ├── Compare datetime → update if changed
            │                                   ├── Compare status  → update if changed (date-based)
            │                                   └── Compare scores  → update if CLOSED
            │
            ├── Future date? ──YES──► _create_heimspiel_scheduled_match()
            │                          ├── Match(status=not_started, scores=0-0, stadium=home_team.stadium)
            │                          ├── MatchMatching(provider=heimspiel)
            │                          └── MCS(all steps=NOT_AVAILABLE)
            │
            └── Past date? ──YES──► create_provider_match() (full pipeline)
                                     ├── Match + MatchMatching
                                     ├── Video ──► SKIPPED (NOT_AVAILABLE)
                                     ├── Period events ──► SKIPPED (NOT_AVAILABLE)
                                     ├── Lineups ──► created from get_match_details_with_players
                                     └── Events ──► created from get_match_details

            After creation/update:
            └── _create_cross_provider_matchings()
                 ├── Parse provider_matchings from Heimspiel API
                 ├── Auto-create MatchMatching for: statsperform(68), wyscout(81),
                 │   sics(102), impect(105), statsbomb(113)
                 └── Auto-create TeamMatching for home/away teams
```

### Status Detection

```
_heimspiel_status(provider_match):
    match.date > now()  →  NOT_STARTED (unplayed/scheduled)
    match.date <= now() →  CLOSED (finished)
```

Heimspiel's `get_matches()` normalizes missing scores to `0`, so score-based detection doesn't work.

### No-Video Provider Handling

```
PROVIDERS_WITH_VIDEO = {SICS, SMRT_STATS}

Heimspiel NOT in PROVIDERS_WITH_VIDEO:
    ├── get_or_create_mcs: status_video = NOT_AVAILABLE, status_period = NOT_AVAILABLE
    ├── create() NOT_FOUND path: skip download_video + create_period_events
    └── _run_post_creation_steps_for_incomplete: force is_video_complete = True
```

---

## Changed Behavior

### Before
- One provider per CE for auto-creation (via MatchCompetitionEditionCreation)
- All matches required video + period events
- Only finished matches could be created
- No match status updates after creation
- Cross-provider matchings created manually

### After
- **Dedicated Heimspiel pipeline** runs independently alongside existing providers
- **No-video providers** skip video/period (status=NOT_AVAILABLE)
- **Unplayed matches** created with status=not_started, MCS all NOT_AVAILABLE
- **Match updates**: datetime, status, scores updated on each cron run
- **Cross-provider matchings** auto-created from Heimspiel's matching data
- **Mutual exclusion** in Forest Admin: Heimspiel ↔ Provider ↔ Wyscout

---

## How to Test in Forest Admin

### Prerequisites
1. A `CompetitionEditionMatching` exists for Heimspiel + target CE
2. `TeamMatching` entries exist for Heimspiel teams (or will be auto-created from cross-provider data)

### Activate Heimspiel Auto-Creation
1. Go to **CompetitionEditionBeating** collection
2. Select a CE (e.g. LaLiga 2025/2026)
3. Click **"Activate auto creation from Heimspiel"**
   - Error if no `CompetitionEditionMatching` for Heimspiel
   - Error if Wyscout or generic provider auto-creation is already active
   - Success: sets `create_matches_from_heimspiel_for_ce_active = True`
4. Lambda runs every 3 minutes — check logs in CloudWatch

### Verify Match Creation
1. Go to **Matches** collection
2. Filter by competition edition
3. New matches should appear with:
   - `status = not_started` (future matches)
   - `status = closed` (past matches with scores)
   - `stadium` = home team's stadium
4. Check **MatchMatching** for each match — should have entries for:
   - `heimspiel`
   - `wyscout`, `statsperform`, `statsbomb`, `impect` (auto-created from Heimspiel data)

### Verify Reports
1. Go to **Provider Match Creation Reports**
2. Filter by `provider = heimspiel`
3. Each Lambda run creates a report with:
   - `count.match_processed` — total matches from Heimspiel
   - `count.action_taken.new_match_created` — newly created matches
   - `count.action_taken.existing_match_updated` — matches with datetime/status/score changes
   - `count.action_taken.no_action` — matches unchanged since last run

### Verify Match Updates
When a scheduled match gets played:
1. Heimspiel's `get_matches()` returns updated scores
2. `_heimspiel_status` detects match date is now in the past → returns `CLOSED`
3. `_update_heimspiel_match` updates:
   - `status`: `not_started` → `closed`
   - `home_team_score` / `away_team_score`: 0 → actual scores
   - `date_time`: if rescheduled
4. Report shows `existing_match_updated` for that match

### Deactivate
1. Click **"Deactivate auto creation from Heimspiel"** on the CE beating
2. Lambda stops processing this CE on next run

### Create a Single Match (Manual)
1. Go to **Matches** collection
2. Click **"Create Match from Provider ID"** (global action)
3. Fill in: Provider=`heimspiel`, Provider Match ID=`11223944`, Competition Edition=LaLiga 2025/2026, Dryrun=True
4. This invokes the `create_match_from_provider` Lambda

### CLI Testing
```bash
# Create a single match (dryrun)
uv run server/manage.py create_match 11223944 --provider heimspiel --season-id 96657 --competition-id 97 --dryrun

# Validate a match
uv run server/manage.py validate_match <match_id>
```

---

## Management Commands

### `create_match`
```
manage.py create_match [provider_match_id] [--provider] [--season-id] [--competition-id] [--dryrun]
```
Defaults: match `11223944`, provider `heimspiel`, season `96657`, competition `97`, dryrun `False`.

### `validate_match`
```
manage.py validate_match <match_id>
```
Runs 12 validation checks: match status, data collection, matchings, MCS completion, video, period events, lineups (11 starters), team kits, stadium, home team side, prepare preprod, full metadata checks.

---

## Test Coverage

**56 tests pass** (11 Heimspiel-specific):

### TestHeimspielNoVideoCreation (3 tests)
- MCS defaults NOT_AVAILABLE for video/period
- Full match creation skips video/period
- Incomplete rerun preserves NOT_AVAILABLE

### TestHeimspielCEMatchCreation (8 tests)
- Scheduled match creation (bare record, NOT_STARTED)
- Dryrun rollback
- Match update: status change (NOT_STARTED → CLOSED)
- Match update: no change
- Match update: datetime change
- Cross-provider matchings created
- Cross-provider matchings handle IntegrityError
- Full CE flow: mixed create + update
