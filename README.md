# Claude Ops Hub

A **project-agnostic** home for driving Claude Code as a personal engineering
assistant. Its job: **observe a set of workspace repos and do real development in
them via on-demand git worktrees, backed by long-term memory** — built almost
entirely from Claude Code plugins and hooks rather than a bespoke backend service.

Nothing in this repo is tied to a particular company or project.

---

## Why this shape (the approach)

The common instinct — a custom FastAPI + Celery + Postgres + pgvector service —
duplicates capabilities Claude Code already ships. This hub instead **wires
together what already exists** and adds only the missing glue:

| Need | What provides it | This hub adds |
|------|------------------|---------------|
| Long-term memory (episodic) | `claude-mem` plugin (SQLite + local Chroma vectors) | nothing — already local |
| Long-term memory (curated) | the `docs/` vault | the taxonomy, hooks and skills that maintain it |
| Isolated work on repos | git worktrees + `superpowers:using-git-worktrees` | the workspace + worktree convention |
| Mirroring the repos | GitLab API | the `/hub-clone-repos` skill |
| Multi-agent orchestration | `superpowers` + `Agent` tool | thin skills over Python workflows |

**No extra database.** `claude-mem` already runs SQLite+FTS5 for keyword search
*and* a local ChromaDB for semantic vectors.

---

## Layout

```
hub/
├── README.md          # this file
├── CLAUDE.md          # how the pieces connect (read this)
├── pyproject.toml     # shared deps + test env; makes hub_lib importable
├── hub_lib/           # stdlib-only shared logic (queue, frontmatter, paths, classify, validate)
├── docs/              # curated Layer-2 memory vault (tracked; see git policy below)
├── workflows/         # full uv-run Python scripts (no JS)
├── tests/             # pytest over hub_lib
├── .claude/
│   ├── settings.json  # wires the doc-sync hooks
│   ├── hooks/         # stdlib-only Python hooks
│   └── skills/        # thin launchers
├── workspace/         # mirrored repo clones (git-ignored)
├── config/            # hub.config.yaml (git-ignored, currently vestigial)
├── data/              # generated outputs (git-ignored)
└── playground/        # disposable/random scripts (git-ignored)
```

All scripting is **Python via `uv`**. Workflows use the root `pyproject`
environment (and may carry PEP 723 headers for portability); hooks are
stdlib-only and run via `uv run --no-project`. **No JavaScript.**

---

## The layered-memory model

Two systems, clear division of labor — don't duplicate between them:

- **`claude-mem` = automatic "what I did."** Captures observations every session
  and injects relevant context at the next `SessionStart`. Zero effort. Backed
  locally by SQLite (keyword) + Chroma (semantic). Historical, **not** authoritative.
- **`docs/` = curated "what the code is and why."** A tracked, plain-Markdown vault
  with a fixed taxonomy (graph, architecture/decisions, domain, workflows, runbooks,
  interfaces, operations, development, generated, memory) and YAML front matter,
  maintained by hub hooks, workflows and skills. Authoritative for current project
  knowledge.

`claude-mem` records *what happened*; `docs/` records *what the code is*.

### `docs/` git policy

`docs/` **is tracked** in git so curated knowledge is shared, backed up and
reviewable — **except** `docs/generated/**` (mechanically regenerated) and
`docs/memory/**` (machine-local sync bookkeeping), which are git-ignored aside
from their `README.md`. Curated knowledge is never silently discarded.

---

## Working loop

1. **Mirror the repos** — `/hub-clone-repos` clones/updates every project under the
   configured `skillcorner` groups into `workspace/<group>/…/<repo>`. It skips any
   repo with uncommitted changes, so it's safe to re-run.
2. **Work in a worktree** — to change a repo, create a git worktree + branch off
   its clone (`EnterWorktree` or `superpowers:using-git-worktrees`). Make changes,
   test, open an MR / merge, then remove the worktree. This keeps the pristine
   `workspace/` clones fast-forwardable and isolates parallel work.
3. **Keep docs in sync** — editing a `workspace/` file appends to the reconciliation
   queue (`docs/memory/pending-updates.jsonl`) via a PostToolUse hook; run
   `/hub-update-project-docs` to reconcile the queue against the final diff and update
   the vault. claude-mem captures the session automatically in parallel.

Need `GITLAB_TOKEN` in the environment for `/hub-clone-repos` (a `read_api` +
`read_repository` PAT). `.claude/hub-env` is a convenience shim.

---

## Skills

`/hub-clone-repos` · `/hub-ingest-repository` · `/hub-update-project-docs` · `/hub-validate-docs`
· `/hub-create-adr` · `/hub-refresh-project-graph` · `/hub-find-project-knowledge`.

Each is a thin launcher: derive args → run a `workflows/` script for deterministic
work → dispatch `Agent` subagents for semantic analysis → summarize. See
`CLAUDE.md` for the full contract of each.

---

## Development

```bash
uv run --dev pytest                  # test hub_lib
uv run workflows/scaffold_docs.py    # (re)build the docs/ vault skeleton
```
