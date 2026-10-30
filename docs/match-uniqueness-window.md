---
repo: [wilson]
mr: [wilson!2695]
verified_at: 2026-10-08
---

# Match uniqueness window (duplicate-match guard)

- `son/models/match.py` `Match._validate_match_uniqueness` (run from `clean`/`save`) rejects a match
  whose home/away pair already has a match within `MATCH_UNIQUENESS_WINDOW` → `MatchAlreadyExists`
  (Gaffer maps it to 400 `match_already_exists`; Forest catches it in `api/forest/match.py`).
- Gaffer and Forest manual creation rely on this guard only. Automated provider matching uses
  ±1 day (`match.py` ~2499, `provider_match_date ± timedelta(days=1)`).
- Was ±12h (also duplicated in `merge_teams`); widened to 24h and shared as one constant in
  wilson MR !2695 (son 0.86.5) after duplicates 2085786/2087803 (2026-10-08).
- The guard is keyed on home/away pair only, not competition edition. Pairs >24h apart
  (the incident pair was 30h) still pass.
