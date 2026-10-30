---
name: hub-distill
description: Distill recent session history into the hub docs/ file lake — promote durable discoveries, features, decisions and root causes from claude-mem and auto-memory project notes into docs/<slug>.md with frontmatter, update MEMORY.md, and lint. Use when the user runs /hub-distill, asks to "distill", "promote memory into docs", "fill the docs lake", or on a periodic schedule.
---

# hub-distill

Batch-promotes knowledge that was captured automatically but never written to
`docs/`. Rules for notes (frontmatter, index, lint) are in the hub `CLAUDE.md`
"Memory" section — follow them exactly.

Argument: a window such as `7d` / `30d` (default `7d`).

## Steps

1. **Baseline.** Run `uv run workflows/lint_docs.py` and read `MEMORY.md`, so you
   know which notes exist and which are stale.

2. **Gather candidates** (read-only):
   - **claude-mem** — load `mcp__plugin_claude-mem_mcp-search__search` /
     `timeline` / `get_observations` via ToolSearch. Search the window for
     observation types discovery 🔵, feature 🟣, decision ⚖️ and bugfix 🔴. Skip
     formatting, test runs and other routine work.
   - **Auto-memory** — `~/.claude/projects/-home-andrei-dev-hub/memory/*.md` with
     `type: project` or `reference`. They describe how systems behave. Leave
     `user` / `feedback` notes where they are, because those describe how to
     work with the user.
   If claude-mem is unavailable, say so and continue with auto-memory only. Never
   invent observations.

3. **Cluster and filter.** Group the candidates by system or topic. Keep a
   cluster only if it would still matter to someone in a month: how something
   works, a root cause, a cross-repo rollout rule, an MR's design or a
   runbook. Drop session chatter and anything the code or git log already says
   plainly.

4. **Verify.** For each kept cluster, check the claims against the current
   source in `workspace/<group>/…/<repo>` (the pristine mirror). Drop or
   correct anything that no longer holds.

5. **Write.** If `MEMORY.md` already covers the topic, update that note and bump
   its `verified_at`. Otherwise create `docs/<slug>.md` with
   frontmatter (`repo`, `mr`, `verified_at` = today) and add one line under
   the right system heading in `MEMORY.md`. Keep notes short and factual,
   with MR refs (`repo!iid`) and `path:line` pointers.

6. **Lint.** `uv run workflows/lint_docs.py` must report 0 errors. Fix any new
   errors you introduced.

7. **Report.** List the notes created and updated (one line each) and the
   candidates you skipped as not durable. Don't commit. The user reviews the
   diff.
