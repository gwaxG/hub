# Claude Ops Hub

A **project-agnostic** home for driving Claude Code as a personal engineering
assistant. Its job: **observe a set of workspace repos and do real development in
them via on-demand git worktrees, backed by long-term memory** — built almost
entirely from Claude Code plugins rather than a bespoke backend service.

Nothing in this repo is tied to a particular company or project.

---

## Why this shape (the approach)

The common instinct — a custom FastAPI + Celery + Postgres + pgvector service —
duplicates capabilities Claude Code already ships. This hub instead **wires
together what already exists** and adds only the missing glue:

| Need | What provides it | This hub adds |
|------|------------------|---------------|
| Long-term memory (episodic) | `claude-mem` plugin (SQLite + local Chroma vectors) | nothing — already local |
| Long-term memory (curated) | `claude-obsidian` plugin | the `wiki/` architecture vault |
| Isolated work on repos | git worktrees + `superpowers:using-git-worktrees` | the workspace + worktree convention |
| Mirroring the repos | GitLab API | the `/clone-repos` skill |
| Multi-agent orchestration | `superpowers` + `Agent`/`Workflow` tools | saved workflow scripts |

**No extra database.** `claude-mem` already runs SQLite+FTS5 for keyword search
*and* a local ChromaDB for semantic vectors. (If Chroma's RAM use bites, switch
`claude-mem` to SQLite-only mode.)

---

## Layout

```
hub/
├── README.md          # this file
├── CLAUDE.md          # how the pieces connect
├── wiki/              # curated long-term-memory vault (Obsidian, git-ignored)
├── workspace/         # mirrored repo clones (git-ignored)
├── workflows/         # full scripts: uv-run Python (no JS)
├── .claude/skills/    # thin launchers (/clone-repos)
├── config/            # hub.config.yaml (git-ignored, currently vestigial)
├── data/              # generated outputs (git-ignored)
└── playground/        # disposable/random scripts (git-ignored)
```

All scripting is **Python via `uv`** (inline PEP 723 deps — no venv, no JS).

---

## The layered-memory model

Two systems, clear division of labor — don't duplicate between them:

- **`claude-mem` = automatic "what I did."** Captures observations every session
  and injects relevant context at the next `SessionStart`. Zero effort. Backed
  locally by SQLite (keyword) + Chroma (semantic).
- **`wiki/` = curated "what the code is and why."** A self-contained Obsidian
  vault (Mode B: codebase / architecture map) that you and Claude maintain via the
  `claude-obsidian` plugin — `ingest` a source, `query` it, `lint` it. Plain
  Markdown you can read in any editor; structure and conventions live in
  `wiki/CLAUDE.md`.

claude-mem records *what happened*; the wiki records *what the code is*.

---

## Working loop

1. **Mirror the repos** — `/clone-repos` clones/updates every project under the
   configured `skillcorner` groups into `workspace/<group>/…/<repo>`. It skips any
   repo with uncommitted changes, so it's safe to re-run.
2. **Work in a worktree** — to change a repo, create a git worktree + branch off
   its clone (`EnterWorktree` or `superpowers:using-git-worktrees`). Make changes,
   test, open an MR / merge, then remove the worktree. This keeps the pristine
   `workspace/` clones fast-forwardable and isolates parallel work.
3. **Remember what matters** — claude-mem captures the session automatically;
   when you learn something durable about a codebase, ingest/update the `wiki/`.

Need `GITLAB_TOKEN` in the environment for `/clone-repos` (a `read_api` +
`read_repository` PAT). `.claude/hub-env` is a convenience shim that pulls it
from your shell profile.

---

## Multi-agent work

- **Ad-hoc parallel work:** the `Agent` tool with a fitting subagent type
  (`Explore`, `Plan`, `code-reviewer`, …).
- **Repeatable fan-out:** `Workflow` scripts in `workflows/`.
- **Isolation:** use git worktrees when several agents edit files in parallel.
