---
repo: [wilson]
mr: [wilson!2845]
verified_at: 2026-11-05
---

# Decommissioning a wilson lambda (prepare_preprod_for_match)

- Wilson lambdas are created from their folder under `pulumi/aws/<group>/<name>/` (`app.py` + `lambda_config.yaml`; `event_bridge.schedule_expression` there makes the cron rule). No central list, so deleting the folder drops the lambda and its EventBridge rule on the next Pulumi deploy.
- Also delete the matching `build:lambda:<name>` job in `cicd/lambda-builds.yml`. The ECR repos `wilson/<name>/<stack>` aren't managed by Pulumi, so delete them by hand.
- `prepare_preprod_for_match` (removed in !2845) only linked or created **Wyscout** videos in Vidic every 3 min. Dead because there's no Wyscout contract, and risky on dev because dev uses the prod Vidic.
- `matchbeating.prepare_preprod_for_match_done` is **not** tied to that lambda: `match_provider_manager` sets it once a match is fully created. Admin filters, match views, `is_match_protected_from_overwrite` and `data_readiness_probe` read it. Keep it.
- Left after !2845 (inert): `prepare_preprod_for_match_active`, Forest `ACTIVATE_PREPARE_PREPROD`, `activate_prepare_preprod` in Wyscout match creation. Removing them needs a migration + son bump; do it with the rest of the Wyscout code.
