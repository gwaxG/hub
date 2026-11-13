---
repo: [wilson, football]
mr: []
verified_at: 2026-11-13
---

# pirlo + francli: the prerelease / deploy / validate loop

Encoded as the global `dev-workflow` skill (`~/.claude/skills/dev-workflow/SKILL.md`). Facts verified 2026-11-10.

- **pirlo** (`uvx pirlo`, also `~/.local/bin/pirlo`) triggers GitLab CI for release, deploy, status, destroy.
  Project and branch come from the git checkout.
  - `release` defaults to `--version prerelease` → `X.Y.Za0+<user>`.
  - `deploy --env other --stack-name X` == `deploy --env X`: any env not in `STANDARD_ENVS` is a custom
    stack (`pirlo/utils.py` `trigger_deploy_gitlab`). It sets `ENV=other` + `PAULUMI_CUSTOM_STACK_NAME`, and paulumi
    swaps the `other` stack name for the custom one (`paulumi.py` `_handle_other_stack`).
  - `destroy --env X` has no `--stack-name`; the env *is* the stack. `--force` also deletes data buckets.
  - `deploy --force` overrides another pipeline's env lock.
- **DB topology**: a custom wilson stack gets its own DB; custom football stacks use the dev DB.
- **Env rule**: every project deploys to its own `mr_<iid>` stack, wilson included. Wilson goes to `dev` only when the
  ticket needs a football pipeline run (football's `mr_<iid>` reads the dev DB). Before deploying to dev, check it with
  `pirlo status`. If it's occupied by an unmerged branch (the usual case), ask first; if it's empty or holds merged
  code, deploy.
- **francli** `football run|status --env`: an enum loaded from francli config. It includes `dev`, `staging`, `prod`
  and personal stacks (e.g. `andrei`). A brand-new stack name may be missing until francli config lists it.
  Success criterion used by the team: the main football pipeline SFN is all green for the finished match.
- **Missing files on dev** (a QA failure caused by the environment, not the change): `s3-copy <preset> --destination-env dev
  --matches <ids>`, from GitLab project `skillcorner/shared/migrate-and-copy`. It invokes the prod lambda
  `wilson-data_copy_tool-prod` (eu-central-1). Presets: match-infos, tracking-extrapolated, physical,
  physical-v301, dynamic-events, gi-*, copy-gt; or `no-preset --skcr-keys BUCKET:PATH`. It never copies to prod.
  `francli football tools migrate-and-copy` is a stub (`NotImplementedError`). For video, see
  `no-video-on-s3-on-dev.md`.
- **QA agents** (global, `~/.claude/agents/`): `qa-planner` turns a diff into `plan.yaml` (http / lambda / pipeline
  steps with oracles; matches from recent green dev runs). `qa/qa_run.py` (PEP 723 script, tests in
  `qa/test_qa_run.py`) executes it deterministically. Before running, it checks the pirlo env git tag (`refs/tags/<env>`,
  moved by the deploy pipeline's `update_tag` stage) equals the branch head. It polls
  `francli football status --format json` (`pipeline_status`, `processed_at`). `qa-verifier` judges the results and posts a short MR note.

## Reaching a custom wilson stack's DB

ECS exec is off on custom stacks, but the Aurora instance `skcr-<stack>-aurora` is publicly accessible. Read
`/<stack>/wilson/DB_CREDS` from Secrets Manager into a 0600 scratch file (it holds `PASSWORD_ARN`, resolved by
the settings) and run a local Django shell from the wilson root:
`AWS_PROFILE=… SKILLCORNER_ENV=dev DJANGO_SETTINGS_MODULE=wilson.settings_local DB_CREDS="$(cat creds.json)"
uv run python server/manage.py shell -c "…"`. Use the root venv (`server/` alone lacks `configargparse`).
Lambdas on a custom stack run with `VIDIC_ENV=prod`: never reach a Vidic push there.
