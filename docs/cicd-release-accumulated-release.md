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

## Mechanics (accumulated-release.yml, job `prepare-release-mr`)
On each push to the default branch, in order:
1. Marks the open release MR `Draft` (merge lock) until the branch is rebuilt.
2. Stops if the tip commit is `chore(release)` (loop guard); it then posts "Released in vX.Y.Z" on the bundled MRs.
3. Stops and closes the release MR if `pyproject.toml` is already ahead of the last tag (manual bump).
4. Counts release-worthy commits since the last tag: only `feat`, `fix`, `perf` and BREAKING. None means no MR.
5. Takes the next version from `git-cliff --bumped-version`.
6. Rebuilds `release-candidate` from `main`: one-line version patch in `pyproject.toml` and `uv.lock`, one commit
   `chore(release): vX.Y.Z`, force-push with `ci.skip`.
7. Creates or updates the MR (changelog as description) and posts "Queued for release, see !N" on each feature MR.
8. Publishes a pre-release `X.Y.Zrc<N>` of the accumulated state (`publish_prereleases`, default true).

## Which change releases the package
The release jobs `build-and-publish` (`uv build` + `uv publish`), `prepare_release_package` (version → `TAG`) and
`release_package` (tag + GitLab Release) run on the default branch with `rules: changes: pyproject.toml`. So the
release is cut by the commit that changes the version on `main`: the merge of the `chore(release)` MR, or a feature
MR with a manual bump. A `pyproject.toml` change without a new version is a no-op (duplicate upload and existing
release are tolerated).

## Contract note from skcr-models!100
`skcr_utils.domain_events.build_domain_event` dumps with `model_dump_json()` and keeps defaults. A producer on a
newer skcr-models therefore sends every new optional field (`physical_events_written: false`,
`match_physical_qi: null`) on every `physical.ready`, v3 ones included. Wilson's contract is `extra='forbid'`, so
the `apply_domain_events` lambda must run the new skcr-models before any football producer of that event relocks.
