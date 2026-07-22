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
Markdown file per note and nothing else — no subfolders, no automation, no
schema. Write a note as `docs/<slug>.md`; keep it current by hand.

Root `MEMORY.md` is the index: one line per file (`[title](docs/slug.md) —
hook`), grouped by system. It is hand-maintained — when you add, rename, or
remove a file in `docs/`, update `MEMORY.md` in the **same** change. Before
adding a note, check `MEMORY.md` and update an existing file rather than
creating a near-duplicate — that discipline is the only thing keeping a flat
lake coherent.

The vault is a best-effort snapshot, **not authoritative** — verify against
current source before trusting a note. (`claude-mem` separately keeps automatic
episodic session history; don't duplicate that here.)

## Secrets

Connector auth lives in the Claude app / MCP connectors, never in this repo.
`GITLAB_TOKEN` comes from the environment (`.claude/hub-env` shim). Never commit
secrets, copy them into notes/prompts/reports, or print full tokens in logs.

## Connector availability

MCP connectors may exist in cloud routines but be absent locally. Tolerate
unavailable connectors, report missing capabilities clearly, prefer
deterministic local alternatives, and **never fabricate connector results**.
