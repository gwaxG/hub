---
repo: [grafana-dashboards]
mr: []
verified_at: 2026-11-24
source: https://skillcorner.slack.com/archives/C021LB81B0C/p1795515635754299
---

# Grafana dashboards via Git Sync

Grafana Git Sync is on for the Main org on prod. Dashboards in the folder `git-sync-org-1` are stored in GitLab repo `devops/monitoring/grafana-dashboards`. The folder groups the platform team dashboards.

## How to change a dashboard

- In the Grafana UI, click Save. Check that you are on the right branch when you save several times.
- Open a MR from the Grafana side or in GitLab. The MR merges without approval.
- GitLab MR is possible too, but you only see the result after the merge.
- The Slack channel `grafana-dashboards-mr` lists the MRs. It compares the dashboard of your branch with the dashboard of `main`.

## What Git Sync does not cover

- **Alerts:** create them in the UI, never in a `git-sync` folder. Git Sync deletes alerts there.
- **Sandbox:** use the `Sandbox` folder in the UI for tests. It is not synced.

## Repo layout (per repo README, checked 2026-11-24)

- `workloads-prod/org-1/` maps to folder `git-sync-org-1` (Main org).
- `workloads-dev/org-1/` maps to `git-sync-org-1-dev`.
- `workloads-prod/common/` maps to `git-sync-common` (Common org, prod only).

Git Sync reads `main` every 60 s. The connection setup is not in IaC. It needs the org Admin role.

## Sources

- Slack announcement by the platform team (Benjamin Kalfa), 2026-11-24. Layout part verified against the repo README. Slack folder name and README connection name match.
