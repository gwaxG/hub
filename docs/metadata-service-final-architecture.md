---
repo: [wilson, football-metadata-service]
mr: []
verified_at: 2026-04-22
---

# Multi-Sport Metadata Service - Final Architecture

## Overview
Extract match creation from Wilson monolith into dedicated pipeline system with centralized metadata service for state tracking and orchestration.

## Core Components

### 1. Metadata Service (New FastAPI Service)

```
Database Schema (RDS PostgreSQL):
┌─────────────────────────────────────────────────────────────────┐
│ match_states                                                     │
├─────────────────────────────────────────────────────────────────┤
│ - id (UUID)                                                      │
│ - match_identifier (sport + provider + provider_match_id)        │
│ - sport (VARCHAR)                                                │
│ - provider (VARCHAR)                                             │
│ - provider_match_id (VARCHAR)                                    │
│ - status (ENUM: pending, processing, completed, failed)          │
│ - error_message (TEXT, nullable)                                 │
│ - created_at (TIMESTAMP)                                         │
│ - updated_at (TIMESTAMP)                                         │
│ - pipeline_execution_arn (VARCHAR, nullable)                     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ competition_editions                                             │
├─────────────────────────────────────────────────────────────────┤
│ - id (UUID)                                                      │
│ - competition_id (VARCHAR)                                       │
│ - edition_id (VARCHAR)                                           │
│ - sport (VARCHAR)                                                │
│ - is_active (BOOLEAN)                                           │
│ - start_date (DATE)                                             │
│ - end_date (DATE)                                               │
│ - created_at (TIMESTAMP)                                         │
│ - updated_at (TIMESTAMP)                                         │
└─────────────────────────────────────────────────────────────────┘

API Endpoints:
- GET /competition-editions/active
- POST /competition-editions/{id}/activate
- POST /competition-editions/{id}/deactivate
- GET /match-states/{match_identifier}
- PUT /match-states/{match_identifier}/status
- GET /match-states?status=failed (for manual retry identification)
```

### 2. Match Discovery Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ Lambda: match-discovery-scanner                                  │
│ (Triggered by EventBridge every 15 minutes)                      │
├─────────────────────────────────────────────────────────────────┤
│ 1. Query Metadata Service for active competition editions        │
│ 2. For each active competition:                                  │
│    - Call data-provider-clients to fetch matches                 │
│    - Build match_identifier (sport + provider + provider_id)     │
│    - Check Metadata Service if match exists                      │
│    - If new: create entry with status='pending'                  │
│    - Enqueue to sport-specific FIFO queue                       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────────┐
    │         FIFO SQS QUEUES (by sport)               │
    ├──────────────────────────────────────────────────┤
    │  - football-matches-queue                        │
    │  - basketball-matches-queue                      │
    │  MessageGroupId: by competition_id               │
    │  DLQ: {sport}-matches-dlq                       │
    └──────────────────────────────────────────────────┘
```

### 3. Busquets-like Dequeuer

```
┌─────────────────────────────────────────────────────────────────┐
│ Lambda: busquets-dequeuer                                        │
│ (Single lambda for all sports)                                   │
├─────────────────────────────────────────────────────────────────┤
│ 1. Poll all sport FIFO queues                                   │
│ 2. Pick one message (match to create)                           │
│ 3. Update Metadata Service: status='processing'                 │
│ 4. Invoke generic pipeline-launcher Lambda                      │
│ 5. On failure → message goes to DLQ                            │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ Lambda: pipeline-launcher (Generic)                              │
├─────────────────────────────────────────────────────────────────┤
│ 1. Determine sport from match data                              │
│ 2. Start appropriate Step Function                              │
│ 3. Pass match_identifier + S3 reference for data               │
│ 4. Store execution ARN in Metadata Service                      │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Pipeline Execution (Step Functions)

```
┌─────────────────────────────────────────────────────────────────┐
│        {SPORT}-MATCH-CREATION-PIPELINE (Step Function)           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  State Data (kept minimal):                                     │
│  {                                                              │
│    "match_identifier": "football_provider1_12345",             │
│    "s3_data_path": "s3://pipeline-temp/matches/xxx.json"       │
│  }                                                              │
│                                                                  │
│  Steps:                                                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ 1. FETCH_FULL_MATCH_DATA                                 │  │
│  │    - Lambda: fetch-provider-match-data                   │  │
│  │    - Calls data-provider-clients                         │  │
│  │    - Stores full data in S3                             │  │
│  │                                                           │  │
│  │ 2. CREATE_OR_UPDATE_TEAMS                               │  │
│  │    - Lambda: process-teams                               │  │
│  │    - Reads from S3, writes to Wilson DB                 │  │
│  │    - Updates S3 with team IDs                           │  │
│  │                                                           │  │
│  │ 3. CREATE_OR_UPDATE_PLAYERS                             │  │
│  │    - Lambda: process-players                             │  │
│  │    - Reads from S3, writes to Wilson DB                 │  │
│  │    - Updates S3 with player IDs                         │  │
│  │                                                           │  │
│  │ 4. CREATE_MATCH                                         │  │
│  │    - Lambda: create-match-wilson                        │  │
│  │    - Reads all data from S3                             │  │
│  │    - Creates match in Wilson DB                         │  │
│  │                                                           │  │
│  │ 5. UPDATE_STATUS                                        │  │
│  │    - Lambda: update-match-status                        │  │
│  │    - Updates Metadata Service: status='completed'       │  │
│  │    - Cleans up S3 temporary data                        │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Error Handling:                                                │
│  - On failure: Update Metadata Service status='failed'          │
│  - Store error details for manual investigation                 │
│  - No automatic retries                                         │
│  - Manual retry via AWS Console or re-enqueueing               │
└─────────────────────────────────────────────────────────────────┘
```

### 5. Data Flow Summary

```
1. Discovery:
   EventBridge → Lambda (scanner) → Metadata Service → SQS FIFO

2. Processing:
   SQS → Busquets Dequeuer → Pipeline Launcher → Step Function

3. Data Storage:
   - Small data: Step Function state (IDs, references)
   - Large data: S3 temporary storage
   - Final data: Wilson PostgreSQL
   - State tracking: Metadata Service PostgreSQL

4. Error Handling:
   - Failed messages → DLQ
   - Failed pipelines → status='failed' in Metadata Service
   - Manual retries only
```

### 6. S3 Structure for Pipeline Data

```
s3://skcr-pipeline-temp/
├── matches/
│   ├── {match_identifier}/
│   │   ├── raw_data.json         # Original provider data
│   │   ├── teams.json            # Processed teams with IDs
│   │   ├── players.json          # Processed players with IDs
│   │   └── match_ready.json      # Final match data for Wilson
```

### 7. Manual Retry Process

```
Options for Failed Matches:

1. Via AWS Console:
   - Find failed execution in Step Functions
   - Click "New Execution" with same input

2. Via Metadata Service Admin:
   - GET /match-states?status=failed
   - Manually re-enqueue to SQS
   - Reset status to 'pending'

3. Via DLQ:
   - Check {sport}-matches-dlq
   - Redrive messages to main queue
```

### 8. Benefits of This Design

- **State Tracking**: Metadata Service prevents duplicates and tracks all matches
- **Data Size Management**: S3 for large data, keeping SFN state minimal
- **Manual Control**: No automatic retries prevents infinite loops
- **Visibility**: Clear status in Metadata Service + Step Function console
- **Separation**: Pipeline orchestration separate from Wilson business logic
- **Generic Components**: Single dequeuer and launcher for all sports

### 9. Implementation Priority

1. **Phase 1**: Metadata Service with competition editions management
2. **Phase 2**: Match discovery scanner + state tracking
3. **Phase 3**: Busquets dequeuer + generic pipeline launcher  
4. **Phase 4**: Football pipeline as proof of concept
5. **Phase 5**: Basketball pipeline
6. **Phase 6**: Migration from Wilson + deprecation