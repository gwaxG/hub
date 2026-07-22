# Claude Ops Hub

A **project-agnostic** home for driving Claude Code as a personal engineering
assistant. Its job: **mirror a set of workspace repos and do real development in
them via on-demand git worktrees** — built from Claude Code's own capabilities
rather than a bespoke backend service.

Nothing in this repo is tied to a particular company or project.

---

## Why this shape (the approach)

The common instinct — a custom backend service to track state — duplicates
capabilities Claude Code already ships. This hub instead **wires together what
already exists** and adds only the missing glue:

| Need | What provides it | This hub adds |
|------|------------------|---------------|
| Isolated work on repos | git worktrees + `superpowers:using-git-worktrees` | the workspace + worktree convention |
| Mirroring the repos | GitLab API | the `/hub-clone-repos` skill |
| Long-term memory (episodic) | `claude-mem` plugin (SQLite + local Chroma) | nothing — already local |
| Long-term memory (curated) | plain files | `docs/` + root `MEMORY.md` — flat, **hand-maintained, no automation** |

There is deliberately no doc-sync automation — the vault is hand-maintained.
Keep it that way unless a real need reintroduces automation as its own decision.

---

## Layout

```
hub/
├── README.md          # this file
├── CLAUDE.md          # how the pieces connect (read this)
├── pyproject.toml     # project metadata only — no importable package
├── MEMORY.md          # hand-maintained navigation index over docs/
├── docs/              # curated Layer-2 memory vault, flat, hand-maintained (tracked)
├── workflows/         # full uv-run Python scripts (no JS)
├── .claude/
│   └── skills/        # thin launchers (currently just hub-clone-repos)
├── workspace/         # mirrored repo clones (git-ignored)
├── config/            # hub.config.yaml (git-ignored, currently vestigial)
├── data/              # generated outputs (git-ignored)
└── playground/        # disposable/random scripts (git-ignored)
```

All scripting is **Python via `uv`**. `workflows/clone_repos.py` is a
self-contained PEP 723 script (its own inline dependency header) — no project
environment to install. **No JavaScript.**

---

## Working loop

1. **Mirror the repos** — `/hub-clone-repos` clones/updates every project under the
   configured `skillcorner` groups into `workspace/<group>/…/<repo>`. It skips any
   repo with uncommitted changes, so it's safe to re-run.
2. **Work in a worktree** — to change a repo, create a git worktree + branch off
   its clone (`EnterWorktree` or `superpowers:using-git-worktrees`). Make changes,
   test, open an MR / merge, then remove the worktree. This keeps the pristine
   `workspace/` clones fast-forwardable and isolates parallel work.
3. **Check `MEMORY.md` before writing anything durable** — it indexes `docs/`
   one line per note. Update an existing note instead of creating a
   near-duplicate, and update `MEMORY.md` in the same change (nothing does
   this automatically). See `CLAUDE.md`'s Memory model section for the full
   convention.

Need `GITLAB_TOKEN` in the environment for `/hub-clone-repos` (a `read_api` +
`read_repository` PAT). `.claude/hub-env` is a convenience shim.

---

## Skills

`/hub-clone-repos` — the only skill in this hub right now. A thin launcher:
derive args → run `workflows/clone_repos.py` → summarize. See `CLAUDE.md` for
the full contract.
