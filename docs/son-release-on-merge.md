---
repo: [wilson, cicd-catalogs]
mr: [wilson!2860, wilson!2875]
verified_at: 2026-11-25
---

# son is released by wilson CI when the MR merges

- **Mechanism**: wilson `.gitlab-ci.yml` includes the `cicd-catalogs/cicd-release` components with
  `pyproject_path: server/pyproject.toml`, `package: son`, `push_pipelines_only: true`.
  - `prepare-release-package` runs on a push to `main` that changes `server/pyproject.toml`. It reads the version and
    sets the tag `v<version>`.
  - `build-and-publish` publishes the son wheel to the GitLab PyPI registry.
  - `release-package` creates the GitLab release and posts to Slack (#python-package).
- **So**: the son version bump in the feature MR (`server/pyproject.toml` + `server/uv.lock`) is the release
  trigger. Merging the MR releases that version. Do **not** run `pirlo release` for the final version; pirlo is only
  for prereleases (`X.Y.Za0+<user>`) before the merge.
- **Evidence**: tag `v0.103.0` points at `9708534f5` (the !2860 merge commit), `v0.102.5` at `5896e4359`, `v0.102.4`
  at `4ac0a148b`: each tag is the merge commit that bumped `server/pyproject.toml`.
- `accumulated-release` is also included (standing `release-candidate` MR, `<next>rcN` publishes, MR title lint,
  scoped to `server/son`). The observed son releases come from the merge commits above.
- **Not automated: the lambda repin.** Lambdas that shipped on a son prerelease keep it until a follow-up MR repins
  them to the released version (lock mechanics: [wilson custom-stack lambda builds](wilson-custom-stack-lambda-builds.md)).
  On 2026-11-25, `main` still pins `son==0.103.0a2+andreimitriakov` in the `pyproject.toml` and `uv.lock` of
  `create_match_from_provider`, `create_matches_from_heimspiel_for_competition_edition` and
  `create_matches_from_provider_for_competition_edition` (!2860 repin not done). !2875 moves their locks to
  `0.104.0a0+andreimitriakov`; after its merge, repin all 3 to `0.104.0`.
