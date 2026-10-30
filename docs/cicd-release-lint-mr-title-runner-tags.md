---
repo: [cicd-catalogs]
mr: [cicd-release!95]
verified_at: 2026-10-13
---

# cicd-release lint-mr-title runner tags

`lint-mr-title` (accumulated-release component) had no `tags:`, so on every MR it fell
through to GitLab SaaS shared runners (`saas-linux-small`) and queued ~15-17 min.
cicd-release MR !95 adds input `lint_tags` (array, default `["eks-small"]`).
`prepare-release-mr` is still untagged (train pushes only) — same fix applies if it queues.
Diagnose: GitLab API `jobs/:id` → `tag_list: []` + `runner.description` contains `saas-linux`.
