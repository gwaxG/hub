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
- **DB topology**: a custom wilson stack gets its own DB; custom football stacks use the dev DB. That's why
  wilson + football features are validated together on `dev` or `staging`.
- **francli** `football run|status --env`: an enum loaded from francli config. It includes `dev`, `staging`, `prod`
  and personal stacks (e.g. `andrei`). A brand-new stack name may be missing until francli config lists it.
  Success criterion used by the team: the main football pipeline SFN is all green for the finished match.
