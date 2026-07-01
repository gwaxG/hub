---
name: daily-brief
description: Run the project-agnostic morning digest — fan out over enabled connectors (Sentry/GitLab/Notion/Slack) and write one HTML brief to data/. Use when the user asks for the daily brief, morning digest, or "what needs attention today".
---

# daily-brief

Runs the `daily-brief` Workflow using values from `config/hub.config.yaml`.
You are the launcher: read the config inline, then invoke the Workflow.

## Steps

1. **Read config → args JSON** (inline; Workflow scripts can't read files, so we
   do it here). This also stamps today's date and reconciles snake_case →
   camelCase for the workflow:
   ```bash
   uv run --with pyyaml python - <<'PY'
   import yaml, json, datetime
   from pathlib import Path
   root = Path.cwd()
   cfg = yaml.safe_load((root / "config/hub.config.yaml").read_text()) or {}
   c = cfg.get("connectors", {}) or {}
   date = datetime.date.today().isoformat()
   out = str((root / cfg.get("output_dir", "./data") / f"digest-{date}.html").resolve())
   s, g, n, sl = (c.get(k, {}) or {} for k in ("sentry", "gitlab", "notion", "slack"))
   print(json.dumps({
     "projectName": cfg.get("project_name", "project"),
     "date": date,
     "outFile": out,
     "connectors": {
       "sentry": {"enabled": bool(s.get("enabled")), "org": s.get("org", ""), "projects": s.get("projects", []) or []},
       "gitlab": {"enabled": bool(g.get("enabled")), "group": g.get("group", ""), "staleMrsDays": g.get("flag_stale_mrs_days", 3)},
       "notion": {"enabled": bool(n.get("enabled")), "watchPages": n.get("watch_pages", []) or []},
       "slack":  {"enabled": bool(sl.get("enabled")), "channels": sl.get("channels", []) or []},
     },
   }))
   PY
   ```
   If `projectName` is `"CHANGEME"` or no connector is enabled, stop and tell the
   user to run `/setup-config` first.

2. **Run the workflow** with that JSON as `args`:
   ```
   Workflow({
     scriptPath: "<repo>/workflows/daily-brief.workflow.js",
     args: <the JSON from step 1, parsed>
   })
   ```

3. **Report** the written path (from the workflow result) and offer to open
   `data/digest-<date>.html`.

## Notes

- Auth for connectors lives in the Claude app / MCP, not this repo. If a reader
  agent returns nothing, the connector is likely unauthenticated in this context
  (common in local runs — see CLAUDE.md).
- To schedule this unattended, register it as a **cloud** routine via `/schedule`.
- Pass a specific day by editing the `date =` line in step 1.
