# CLAUDE.md — Claude Ops Hub

This repository is a **project-agnostic control layer for Claude Code**, not an
application. It mirrors GitLab repos locally and gives Claude Code an isolated,
on-demand Git worktree to do real work in them. Read `README.md` for the full
rationale.

## Language and runtime

All committed automation is Python via `uv`. `workflows/clone_repos.py` is a
self-contained PEP 723 script — `uv run workflows/clone_repos.py` needs nothing
installed. Root `pyproject.toml` is metadata only (`[tool.uv] package = false`).
**No JavaScript or TypeScript.** Deterministic work belongs in Python; don't ask
an LLM to do what Python can do reliably.

## Working on the hub itself

You create worktrees in the folder /worktrees. 
You do the implementation, create a branch, commit and push to origin, open MR, assign to me - "andrei.mitriakov@skillcorner.com".

## Working on workspace repositories

`workflows/clone_repos.py` mirrors every GitLab project under the configured
`skillcorner` groups into `workspace/<group>/…/<repo>` (needs `GITLAB_TOKEN` in
the environment; `--dry-run` previews). The mirror is a **pristine
synchronization target** — do not do feature work in it.

To modify a repo: create an isolated Git worktree + branch (`EnterWorktree` or
`superpowers:using-git-worktrees`), make changes there, run tests/linters,
inspect the final diff, open an MR, wait for merging, then remove the worktree.
This keeps `workspace/` clones fast-forwardable and isolates parallel work.

Do **not** commit feature changes from a mirror, leave untracked files in a
mirror, reset/clean a dirty repo, reuse an unrelated worktree, or modify a
default branch unless explicitly told to.

## Memory — the `docs/` file lake

Durable project knowledge lives as a flat **file lake**: `docs/` holds one
Markdown file per note and nothing else — no subfolders. Write a note as
`docs/<slug>.md`, starting with this frontmatter:

```
---
repo: [wilson, football]        # repos/systems the note is about (hub for the hub)
mr: [wilson!2664, football!1575] # MRs it describes, [] if none
verified_at: 2026-10-30          # last date checked against source
---
```

Optional `source:` holds Slack/Notion permalinks. Bump `verified_at` whenever you
re-check a note against code. `uv run workflows/lint_docs.py` checks frontmatter,
dead links, orphans (files missing from `MEMORY.md`) and stale notes (>90 days);
run it after every docs change — errors must be zero.

Root `MEMORY.md` is the index: one line per file (`[title](docs/slug.md) —
hook`), grouped by system. It is hand-maintained — when you add, rename, or
remove a file in `docs/`, update `MEMORY.md` in the **same** change. Before
adding a note, check `MEMORY.md` and update an existing file rather than
creating a near-duplicate — that discipline is the only thing keeping a flat
lake coherent.

The vault is a best-effort snapshot, **not authoritative** — verify against
current source before trusting a note. (`claude-mem` separately keeps automatic
episodic session history; don't duplicate that here.)

The index is imported below, so every hub session starts with it loaded:

@MEMORY.md

Write memory files into /docs in cases when:
  (1) you discover new things about existing codebase like behaviour, workflows etc;
  (2) you implement something new in codebase like features, workflows etc.
Remove or modify obsolete files if they do not correspond to the reality.

Ingestion paths: by hand while working; the Stop hook
(`.claude/hooks/docs_nudge.py`) asks to record learnings at the end of a turn
when the work since its last nudge was costly (code edits, commits or MR calls;
or an investigation of 25+ tool calls, a subagent, or 20+ minutes) and wrote
nothing to `docs/`; `/hub-distill` batch-promotes
claude-mem history and auto-memory project notes; `hub-slack-ingest` files
durable facts whenever the user asks about Slack.

## Secrets

Connector auth lives in the Claude app / MCP connectors, never in this repo.
`GITLAB_TOKEN` comes from the environment (`.claude/hub-env` shim). Never commit
secrets, copy them into notes/prompts/reports, or print full tokens in logs.

## Connector availability

MCP connectors may exist in cloud routines but be absent locally. Tolerate
unavailable connectors, report missing capabilities clearly, prefer
deterministic local alternatives, and **never fabricate connector results**.
