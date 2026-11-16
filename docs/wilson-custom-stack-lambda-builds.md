---
repo: [wilson]
mr: [wilson!2867]
verified_at: 2026-11-13
---
# Wilson lambdas on a pirlo custom stack

- `cicd/lambda-builds.yml` is **generated** by `cicd/generate_ci_build_jobs.py` (never hand-edit). Each `build:lambda:*` job's `when: never` ENV rule comes from the lambda's `lambda_config.yaml` `environments` (`generate_ci_build_jobs.py:201-206`).
- To build a lambda on a custom stack, add to `environments` (temporary, remove before merge) both the stack name (e.g. `mr-2867`) and `other` (custom-stack pipelines run with `ENV=other`, `generate_ci_build_jobs.py:179`). Regenerate from repo root: `uv run --no-project --with pyyaml python cicd/generate_ci_build_jobs.py` and commit the result. Without it the job never runs and Pulumi falls back to the shared `prod` image.
- Ship a son/dpc prerelease in a lambda by changing only its `uv.lock` (`uv lock --prerelease=if-necessary-or-explicit -P son`, = `poe lock_all -u son`); never edit its `pyproject.toml` (opens prereleases for transitive deps, e.g. `skcr-models 0.38.0a0`). Check every lock for unintended prereleases afterwards.
- Custom stack names: lowercase letters, digits, hyphens only (`mr-2867`, not `mr_2867`).
- Keep one commit (the branch gets squashed); re-release son with pirlo after the final lock change.
- See [pirlo + francli dev loop](pirlo-francli-dev-loop.md).
