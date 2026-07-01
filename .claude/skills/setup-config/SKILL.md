---
name: setup-config
description: Interactively create or update config/hub.config.yaml — the single project-specific file for the Claude Ops Hub. Asks for the project name and which connectors (Sentry/GitLab/Notion/Slack) to enable, then writes and validates the file. Use during first setup or to repoint the hub at a different project.
---

# setup-config

Creates the ONE config file the hub reads: `config/hub.config.yaml`.
You are the interviewer; `workflows/setup_config.py` does the writing/validation.

## Steps

1. **Ask the user** (use the AskUserQuestion tool, or just ask in chat):
   - Project name (human-readable; used in digest titles).
   - Which connectors to enable: Sentry, GitLab, Notion, Slack.
   - For each enabled connector, the non-secret selector:
     - Sentry → org slug (+ optional project list)
     - GitLab → top-level group (+ optional stale-MR days, default 3)
     - Notion → optional page/database IDs to watch
     - Slack → channel names to skim
   - Do **not** ask for tokens/auth — those live in the Claude app / MCP connectors.

2. **Build the answers JSON** in this shape:
   ```json
   {
     "project_name": "My Project",
     "connectors": {
       "sentry": {"enabled": true, "org": "my-org", "projects": ["backend"]},
       "gitlab": {"enabled": true, "group": "my-group", "flag_stale_mrs_days": 3},
       "notion": {"enabled": false, "watch_pages": []},
       "slack":  {"enabled": false, "channels": []}
     }
   }
   ```

3. **Write + validate** by piping that JSON to the script:
   ```bash
   echo '<answers-json>' | uv run workflows/setup_config.py write
   ```
   The script deep-merges onto safe defaults, writes `config/hub.config.yaml`,
   and prints any errors/warnings.

4. **Report** the result. If it printed errors, quote them and offer to re-run
   with corrected answers. On success, tell the user the hub is ready and they
   can run `/daily-brief`.

## Notes

- The file is git-ignored — it may hold selectors you shouldn't guess. Confirm
  values with the user before writing.
- Re-running is safe: it overwrites `config/hub.config.yaml` with the new answers
  (merged onto defaults), so it doubles as "repoint the hub at another project".
- To only re-check an existing file without rewriting it:
  ```bash
  uv run workflows/setup_config.py validate
  ```
