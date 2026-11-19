---
repo: [wilson]
mr: [wilson!2875]
verified_at: 2026-11-19
---

# Heimspiel split seasons and 1-to-N CE mapping

Heimspiel exposes one "season" (provider CE) per phase for many Latin American leagues. SkillCorner models one
CompetitionEdition (CE) per year. Facts from read-only Heimspiel calls and the dev DB on 2026-11-12.

- Heimspiel competition 100 is **Peru** (2026: 113359 Apertura + 123460 Clausura, 153 matches each, no shared match ids).
  Chile is competition 98, single 2026 season 112378 (SC CE 1406).
- Splits: PER/PAR Apertura+Clausura; COL Apertura + Apertura Playoffs + Clausura; URY Apertura/Intermedio/Clausura;
  ARG/MEX/CRI Apertura and Clausura each with Playoffs; MLS/BRA/ECU season + Playoffs. SmrtStats and Wyscout: one CE per season.
- Dev DB already has separate "X Clausura" SC CEs holding the Clausura ids (1750 PER, 1751 COL, 1752 PAR, 1753 URY,
  1756 ARG, 1763 URY Intermedio). Moving them into the base CE is out of scope of Task 4107.
- Heimspiel season dates cover the whole year; Clausura "Round N" collides with Apertura; Playoffs use matchday 0/1/2.

## wilson!2875 (Task 4107), scope agreed 2026-11-19
- Migration 0290 drops unique `(competition_edition, provider)` on `CompetitionEditionMatching`, keeps
  `(provider, provider_competition_edition_id)`. son 0.103.0.
- N is used only by `create_provider_matches_from_ce` (both CE creation lambdas), the Heimspiel metadata cron
  (`update_created_matches`, keyed by the tuple of a CE's matchings) and `force_match_metadata_update`.
  Helper `get_provider_matches_for_competition_editions`: dedupe by provider match id, skip+log a failed fetch,
  raise only if all fail, re-raise `ApproachingTimeoutError`. SICS keeps one call (ignores the CE id).
- **Forest, Gaffer, `create_match_from_provider` and the public serializer are deliberately unchanged** (user decision).
  Gaffer still rejects two matchings of one provider, so N rows are created via DB/admin. Forest `.get()` on such a CE
  raises `MultipleObjectsReturned`.
- `update_matches_metadata` is an ECS task (`ecs/management/commands/update_matches_metadata.py`, IaC
  `pulumi/aws/management/update_matches_metadata/ecs_task_config.yaml`, every 6 h, prod+dev only); on a custom stack run
  it by hand. The cron writes 2 `MetadataUpdateHistory` rows per checked match (fields + locked fields) by design.
- The SICS dry run on CE 1382 shows 10 `TransactionManagementError` failures on main too (pre-existing).
- Validated on custom stack `andrei` with COL 1382 (+HS 120131), MLS 1393 (+HS 132264) and Chile 1406; the two extra
  matchings were left in the andrei DB.
