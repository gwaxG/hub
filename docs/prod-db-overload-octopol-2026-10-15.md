---
repo: [wilson]
mr: [wilson!2722]
verified_at: 2026-10-15
---

# Prod DB overload → gaffer 504s (2026-10-15)

Incident 02:00–03:57 UTC: `skcr-prod-aurora` (single writer, db.r8g.2xlarge, no reader) saturated twice;
engine restarted 02:39:33 UTC (FreeableMemory 17 GB → 0.46 GB, connections 60 → 473, db.load ≈ 370 AAS).

Cause: client `octopol.io` running 6 accounts (`igor@`, `igor1..5@`) in parallel against the public API:
- 02:00 window: `/api/players/` with a huge `competition_edition IN (...)` filter → `COUNT(*)` over api_player ⋈ api_playermatching; ~21 min per request.
- 03:00 window: `/api/matches/?user=true&matching=wyscout&limit=1000&offset=N` deep OFFSET pagination (offset up to 178000); ~26 min per request.

Impact: `/gaffer/*` pages hung up to ~22 min for 5 external operators → 504 at the edge. Sentry only shows
the side-effects (`connection timeout expired`, `SSL SYSCALL error: EOF`, `the connection is closed`) in
Lambdas at the restart.

Gaps: no DB `statement_timeout` (queries outlive the HTTP 504), no per-account/org throttle, no
error-rate/latency alerts. Octopol's normal day: ~120–200k requests, max ~30–120 s.

How to investigate the next one (eu-central-1, `AWS_PROFILE=Production.Skcr-Software-Common-Role`):
`aws rds describe-events`, CloudWatch AWS/RDS metrics, Performance Insights
(`aws pi describe-dimension-keys --group-by db.sql|db.application`), Logs Insights on log group `wilson-prod`
(`stats sum(seconds_elapsed) by user_info.username, endpoint`). Sentry API works from a logged-in
browser via `fetch('/api/0/organizations/skillcorner/issues/?project=4505912184012800')`.

Follow-up: wilson !2722 (draft) — `DB_STATEMENT_TIMEOUT_MS=55000` on the app ECS service only (Redis-cached
pagination COUNT was tried and dropped). Lowering `max_limit`/capping `offset` was rejected: 600+ users
send `limit` ≥ 10000 and ~15 clients legitimately page `/api/players/` to offset ~206k. Remaining ideas:
per-org throttle/concurrency cap, spoofable Referer bypass in `api/throttling.py:can_bypass_throttle`, DB alarms, reader.
