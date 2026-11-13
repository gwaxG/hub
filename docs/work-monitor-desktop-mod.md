---
repo: [hub]
verified_at: 2026-11-13
---

# work-monitor: Claude desktop side pane (mod)

A Claude Code **mod** (function-hooks plugin) that draws a pane beside the chat: other desktop sessions, active/failed CI, my open MRs, review-requested MRs. Polls every 60s; `/work-monitor` reopens it.

- **Location**: written by the `plugin-authoring` skill into `~/.claude/dev-mods/<session-id>/work-monitor/` (session-scoped hot-reload). To get it in every session, name the folder in `CLAUDE_CODE_PLUGIN_DIRS` (env block of `~/.claude/settings.json`) or install it from a folder marketplace.
- **Files**: `hooks/register.tsx` (pane, poll, `/work-monitor`), `hooks/sources.ts` (data), `types/index.d.ts` (`$.state` contract), `tests/pane.test.tsx`.
- **Sessions**: `$.mcp.call('ccd_session_mgmt', 'list_sessions', { limit })` — the desktop app's own MCP server; returns JSON text (`sessionId, title, isRunning, isArchived, lastActivityAt, group{name}, link`). Excludes the calling session. Unverified that a mod can reach this server live; the pane shows "Sessions: session list unavailable" if not.
- **GitLab**: one GraphQL POST to `gitlab.com/api/graphql` — `currentUser { authoredMergeRequests / reviewRequestedMergeRequests (state: opened, sort: UPDATED_DESC) { iid title webUrl draft project{fullPath} headPipeline{status path} } }`. There is no cross-project "my running pipelines" endpoint, so "active CI" = MR head pipelines in CREATED/PENDING/RUNNING/…
- **Token**: the desktop app does not source `~/.bashrc`, so `$.env.get('GITLAB_TOKEN')` is usually empty; the mod parses the `export GITLAB_TOKEN=` line from `~/.bashrc` (same trick as `.claude/hub-env`).
- **Dev loop**: `claude plugin validate <dir>`; `tsc -p` with a tsconfig outside the mod including the skill's `types/claude-code.d.ts`; `claude plugin test <dir>` (mock `mcp.call`, `http.fetch`, `env.get` with `on(...) => ({ value })`, then `ui.press({ key: 'refresh' })`).
- **Gotchas**: section children must be typed `RenderChildren[]`, not `unknown[]`; MCP text blocks need a `block.text` truthiness check under strict mode.
