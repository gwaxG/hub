---
repo: [wilson, grafana-dashboards]
mr: [grafana-dashboards!122, grafana-dashboards!132, grafana-dashboards!133, wilson!2967]
verified_at: 2026-11-26
---

# Wilson backend serving dashboard and alert rules

Where the Wilson backend serving dashboard and its alert rules live now, and how to check them.

- **Source of truth:** `workloads-prod/org-1/App Workloads/wilson/wilson-backend-serving.json` in grafana-dashboards (uid `wilson-backend-serving`). Grafana Git Sync loads it from `main` every 60 seconds.
- **Content:** 19 panels in four rows: Health metrics, Latency of 2xx, Server errors 5xx, Client errors 4xx. Each row has Dynamic events, Physical and Game intelligence panels. The title and uid do not change.
- **Open MR:** grafana-dashboards !132 replaces the old prod panels with the branch panels. Check it in the Grafana preview after merge.
- **Dev draft:** `wilson-backend-serving-dev` was deleted from `main` by grafana-dashboards !122. Git Sync removes it from Grafana. Do not recreate it without a reason.
- **Wilson copies:** wilson !2967 deletes the five dashboard JSON files from `grafana/dashboards/`. The grafana-dashboards repo is the only source after it merges.
- **Alert rules:** made in the Grafana UI, not in code. Folder `Alerts App Workloads/wilson`, group `wilson-alerts`, evaluated every 5 minutes.
  - *Wilson API health below 95%*: Athena on ALB logs, fires below 0.95 for 10 minutes.
  - *Wilson API 401/403 spike*: fires above 5,000 per 5-minute bucket for 10 minutes. The 7-day `/api/` baseline is median 161, p99 4,006, max 9,981.
  - Both route to contact point `sns-wilson-backend`, which publishes to SNS `wilson-backend-alerts-prod` (product-area backend Slack channel).
- **Rule doc:** grafana-dashboards !133 records the live rules (rule uids `fg5aczw71s0sge`, `ag5aczwfxf11cd`, folder `eg5aczvyq47b4c`), checked against the API on 2026-11-26.
- **State 2026-11-26:** both rules evaluate with health `ok` and state Normal. No test notification has reached SNS yet. The rules once disappeared without explanation, so check them through the API after any change.
- **Evaluation state:** `fetch('/api/prometheus/grafana/api/v1/rules')` shows state, health and last error per rule.

**How to check from a logged-in browser:** the Grafana UI often fails to load in the browser pane. Use the API instead:
- `fetch('/api/v1/provisioning/alert-rules')` lists rules.
- `fetch('/api/folders?limit=100')` lists folders.

**Repo preview link:** `{grafana}/dashboard/provisioning/<repository>/preview/<path>?ref=<branch>`. Strip the `workloads-prod/org-1/` prefix from the path, and encode spaces as `%20`. The prod repository is `repository-889f620`. A "file not found" page means the path or the repository is wrong.

**Why:** the dashboard and the alert rules have no single source. Dashboards come from the repo, but alert rules exist only in Grafana.

**How to apply:** change dashboards by MR to grafana-dashboards `main`. Change alert rules in Grafana, then check them through the API. Do not assume a rule exists until the API shows it.

See also [[wilson-data-readiness-probe]].
