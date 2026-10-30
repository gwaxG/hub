---
repo: [wilson, football-metadata-service]
mr: []
verified_at: 2026-04-22
---

# Multi-Sport Metadata Service Architecture

## Overview
Extract match creation from Wilson monolith into dedicated pipeline projects per sport, similar to the existing football pipeline architecture.

## Architecture Components

### 1. Core Services

```
┌─────────────────────────────────────────────────────────────────┐
│                         METADATA SERVICE                         │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  API Layer (FastAPI)                                     │  │
│  │  - GET /matches/{match_id}                              │  │
│  │  - POST /matches (individual creation)                  │  │
│  │  - GET /players/{player_id}                            │  │
│  │  - GET /teams/{team_id}                               │  │
│  │  - GET /competitions/{competition_id}                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Database Layer (PostgreSQL via son/Django ORM)         │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Match Discovery & Orchestration

```
┌─────────────────────────────────────────────────────────────────┐
│                    MATCH DISCOVERY SERVICE                       │
├─────────────────────────────────────────────────────────────────┤
│  Lambda: match-discovery-scanner                                 │
│  - Runs on schedule (EventBridge: every 15 min)                 │
│  - Checks active competition editions                           │
│  - Queries data providers for new matches                      │
│  - Compares with existing DB                                   │
│  - Publishes to sport-specific queues                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────────┐
    │              SQS QUEUES (by sport)               │
    ├──────────────────────────────────────────────────┤
    │  - football-matches-to-create                     │
    │  - basketball-matches-to-create                   │
    └──────────────────────────────────────────────────┘
```

### 3. Pipeline Workflow (Per Sport)

```
┌─────────────────────────────────────────────────────────────────┐
│           SPORT-SPECIFIC MATCH CREATION PIPELINE                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Lambda: {sport}-pipeline-trigger                               │
│  - Triggered by SQS: {sport}-matches-to-create                  │
│  - Starts Step Function execution                               │
│                            │                                     │
│                            ▼                                     │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              STEP FUNCTION WORKFLOW                       │  │
│  ├──────────────────────────────────────────────────────────┤  │
│  │                                                           │  │
│  │  1. FETCH_MATCH_DATA                                     │  │
│  │     └─> Lambda: fetch-provider-data                      │  │
│  │         - Get match details from data provider           │  │
│  │                                                           │  │
│  │  2. CREATE_TEAMS                                         │  │
│  │     └─> Lambda: create-or-update-teams                   │  │
│  │         - Call Metadata Service API                      │  │
│  │         - Create/update home & away teams                │  │
│  │                                                           │  │
│  │  3. CREATE_PLAYERS                                       │  │
│  │     └─> Lambda: create-or-update-players                 │  │
│  │         - Call Metadata Service API                      │  │
│  │         - Process squad lists                            │  │
│  │                                                           │  │
│  │  4. CREATE_MATCH                                         │  │
│  │     └─> Lambda: create-match                             │  │
│  │         - Call Metadata Service API                      │  │
│  │         - Create match entity                            │  │
│  │                                                           │  │
│  │  5. ENRICH_MATCH_DATA                                    │  │
│  │     └─> Lambda: enrich-match-metadata                    │  │
│  │         - Add sport-specific metadata                    │  │
│  │         - Stadium info, referee info, etc.              │  │
│  │                                                           │  │
│  │  6. NOTIFY_COMPLETION                                    │  │
│  │     └─> Lambda: notify-match-ready                       │  │
│  │         - Send to SNS topic                              │  │
│  │         - Update pipeline status                         │  │
│  │                                                           │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Queue Management Strategy

```yaml
Queues:
  Discovery:
    - competitions-to-scan (FIFO)
      - MessageGroupId: by sport
      - VisibilityTimeout: 60s
      - DLQ: competitions-scan-dlq
  
  Match Creation:
    - {sport}-matches-to-create (Standard)
      - VisibilityTimeout: 300s
      - MessageRetention: 14 days
      - DLQ: {sport}-matches-dlq
      - Redrive: 3 attempts
  
  Pipeline Status:
    - pipeline-status-updates (FIFO)
      - For monitoring and alerting
      - MessageGroupId: by match_id
  
  Error Handling:
    - match-creation-errors (Standard)
      - Manual review queue
      - Connected to alerting
```

### 6. Data Flow

```
1. Discovery Flow:
   EventBridge → Lambda (scanner) → SQS (per sport) → Lambda (trigger)

2. Pipeline Flow:
   Lambda (trigger) → StepFunction → Multiple Lambdas → Metadata Service API

3. Status Flow:
   StepFunction → SNS → Status Queue → Monitoring Dashboard
```

### 7. Benefits of This Architecture

#### Visibility
- Each match creation is a separate Step Function execution
- Easy to track in AWS Console or custom dashboard
- Clear error identification per match

#### Separation of Concerns
- Pipeline: Handles mass creation, orchestration
- Metadata Service: Data storage, individual CRUD operations
- Sport projects: Sport-specific logic isolated

#### Scalability
- Queue-based decoupling prevents overload
- Parallel processing per sport
- Rate limiting via queue configuration

#### Multi-Sport Support
- Common pattern across all sports
- Sport-specific customization in dedicated projects
- Shared components via skcr-utils

### 8. Migration Strategy

1. **Phase 1**: Build Metadata Service API
   - Extract current match creation logic from Wilson
   - Create FastAPI service with existing Django ORM models

2. **Phase 2**: Implement Discovery Service
   - Lambda for scanning competitions
   - Queue setup per sport

3. **Phase 3**: Create Football Pipeline Enhancement
   - Add match creation workflow to existing football project
   - Test with real data

4. **Phase 4**: Roll out other sports
   - Basketball, Hockey, Handball projects
   - Reuse football patterns

5. **Phase 5**: Deprecate Wilson match creation
   - Switch to new pipeline
   - Monitor for issues

### 9. Monitoring & Observability

```
Dashboards:
- Match creation rate per sport
- Pipeline success/failure rates
- API latency metrics
- Queue depth monitoring

Alerts:
- DLQ messages > threshold
- Pipeline failures > threshold
- API errors > threshold
- Match creation lag > threshold
```

### 10. Infrastructure as Code (Pulumi)

```python
# Example structure for paulumi integration
class SportPipeline:
    def __init__(self, sport: str):
        self.sport = sport
        self.create_queues()
        self.create_lambdas()
        self.create_step_function()
    
    def create_queues(self):
        # SQS queues for match creation
        pass
    
    def create_lambdas(self):
        # Pipeline trigger and workflow steps
        pass
    
    def create_step_function(self):
        # Orchestration workflow
        pass
```
