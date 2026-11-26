---
repo: [cicd-catalogs, skcr-models]
mr: [skcr-models!99, skcr-models!100, skcr-models!101]
verified_at: 2026-11-26
---

# cicd-release accumulated release (the "MergeBot" / release bot)

Checked 2026-11-26 against cicd-catalogs `cicd-release/templates/accumulated-release.yml` and skcr-models `main`.

- **What it is.** A CI job, not a GitLab app. skcr-models `.gitlab-ci.yml` includes the component
  `cicd-release/accumulated-release`. Its job `prepare-release-mr` runs on every push to the default branch.
- **What it does.** With git-cliff it reads the Conventional Commits since the last tag, computes the next version,
  and keeps one standing MR open: branch `release-candidate` → `main`, title `chore(release): vX.Y.Z`
  (bumped `pyproject.toml` + lock + changelog). `feat` gives a minor bump, `fix` a patch, `chore(deps)` no release.
- **Identity.** It uses the `RELEASE_BOT_TOKEN` CI variable (group access token). Its commits and MRs show the
  author `RELEASE_BOT_TOKEN` (`group_60939462_bot_…`).
- **A human still merges the release MR.** Example: !99 `chore(release): v0.41.0` was merged by hand. After that
  merge, `prepare-release-package` + `release-package` tag the commit and publish the package.
- **So a feature MR does not bump the version.** A merged feature is not installable until the release MR is
  merged too (skcr-models!100 merged at 0.41.0; 0.42.0 waits in !101).
- **Manual bump still works.** If a feature MR bumps `pyproject.toml` itself, the per-merge release path cuts the
  release at once and the accumulator stands down.
- **MR titles matter.** The `lint-mr-title` job enforces Conventional Commit titles, because the squash title
  drives the bump and the changelog (see [lint-mr-title runner tags](cicd-release-lint-mr-title-runner-tags.md)).

## Contract note from skcr-models!100
`skcr_utils.domain_events.build_domain_event` dumps with `model_dump_json()` and keeps defaults. A producer on a
newer skcr-models therefore sends every new optional field (`physical_events_written: false`,
`match_physical_qi: null`) on every `physical.ready`, v3 ones included. Wilson's contract is `extra='forbid'`, so
the `apply_domain_events` lambda must run the new skcr-models before any football producer of that event relocks.
