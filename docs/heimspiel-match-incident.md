---
repo: [data-provider-clients]
mr: [data-provider-clients!43]
verified_at: 2026-10-05
---

# Heimspiel match incident & finished-with-coverage

Heimspiel's `/match` payload has an optional `match_incident {id, name, shortname}` (catalogue: `/match-incident`).
It holds disruptions **and** outcome annotations (e.g. id 12 "nach Verlängerung" = after extra time). Names are localised — map by id.

data-provider-clients 1.13.0 (MR shared/data-provider-clients!43) adds to common `Match`:

- `incident: Literal['rescheduled', 'suspended', 'did_not_play', 'annulled'] | None` — ids 3/4/6/7
  (`COMMON_INCIDENT_BY_ID` in `models/heimspiel/match_incident.py`); any other id → None.
- `is_finished_with_coverage: bool | None` (same name on Heimspiel `DetailedMatch` and common `Match`) — `finished == "yes" and live_status == "full"` (PM rule); None when `finished` absent.
  `live_status` is coverage (`none|result|goals|data|full`), so a finished low-tier match with result-only coverage is `is_finished_with_coverage=False`.
- SICS / SmrtStats leave both None (SmrtStats has a raw `Match.status`, unmapped).

Set in both `_to_common_match` (get_matches / get_match_common) and `get_match_details`.
Consumer: wilson Heimspiel cron, Notion task "Handle postponed and canceled matches" (incident 6/7 → canceled/not_available,
3/4 → postponed, rescheduled tracked past D+7 until played, then D+7 of the actual date).

Open: whether Heimspiel clears `match_incident` after a rescheduled match is replayed — unverified.
