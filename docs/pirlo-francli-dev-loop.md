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
- **QA agents** (global, `~/.claude/agents/`): `qa-planner` turns a diff into `plan.yaml` (http / lambda / pipeline
  steps with oracles; matches from recent green dev runs). `qa/qa_run.py` (PEP 723 script, tests in
  `qa/test_qa_run.py`) executes it deterministically. Before running, it checks the pirlo env git tag (`refs/tags/<env>`,
  moved by the deploy pipeline's `update_tag` stage) equals the branch head. It polls
  `francli football status --format json` (`pipeline_status`, `processed_at`). `qa-verifier` judges the results and posts a short MR note.
