---
repo: [maldini-api, argocd]
mr: [maldini-api-chart!60, maldini-api-chart!61]
verified_at: 2026-11-04
---

# argocd charts are per-project; maldini prod roll

- `skillcorner/devops/argocd` is a GitLab **group**, one project per chart (`.../maldini-api`, `.../kaka`, `.../loki`, …). Cloning the group path as a repo fails. In the mirror, `workspace/skillcorner/devops/argocd/` has no `.git`; each chart subdirectory is the clone.
- **maldini-api prod roll** is a hand-written chart MR, not CI-generated (unlike football-metadata-service, where CI `update-helm` opens it): bump `image.tag` and `cronjob.image.tag` in `values.prod.yaml`, branch `feat/update-<ver>`, title `Update image to <ver>` (!60 = 1.7.4, !61 = 1.7.5).
- Image tag = app `pyproject` version, so every maldini-api release MR must bump the version and run `uv lock`.
- Merge the chart MR only after the app's main `build` job has pushed the tag. Dev tracks `latest` (pullPolicy Always), no MR needed.
- The mirror goes stale fast: it still shows 1.7.4 (`values.prod.yaml:6,100`). Fetch before assuming a version.
