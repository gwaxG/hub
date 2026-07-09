# CLAUDE.md — Claude Ops Hub

This repo is a **project-agnostic control layer for Claude Code**, not an app.
It wires together capabilities Claude Code already ships (claude-mem, MCP
connectors, the `Agent` tool, git worktrees) and adds only the glue.
Read `README.md` for the full rationale.

Its job today: **observe the workspace repos and do real work in them via
on-demand git worktrees, backed by long-term memory.**

## Language

**All scripting is Python, run via `uv`** (`uv run ...`), with dependencies
declared inline via PEP 723 headers — no venv, no `pyproject.toml`, no committed
Python package. **No JavaScript.** LLM fan-out (analyzing many repos, etc.) is
done by dispatching the **Agent tool** from the launching skill, while the
committed Python script owns the deterministic work (discovery, file I/O).

## Where code goes

- **One-liner → a skill.** A short inline snippet goes directly in the skill as a
  `uv run --with … python - <<'PY' …` block.
- **More than a one-liner → `workflows/`.** Anything substantial is a committed
  **Python** script under `workflows/` (`uv run`). Skills stay thin: they run the
  Python script for deterministic work and dispatch Agent subagents for LLM work.

## Memory: two layers, no overlap

- **claude-mem** = automatic "what I did." Captured every session, re-injected
  at `SessionStart`. Zero effort. Local SQLite + Chroma. It provides its own
  session-start context injection — the hub adds no memory hooks of its own.
- **`wiki/`** = curated "what the code is and why." A self-contained **Obsidian
  vault** (Mode B: codebase / architecture map) at `~/dev/hub/wiki/`, maintained
  by you and Claude via the `claude-obsidian` plugin (`ingest`, `query`, `lint`).
  It is **git-ignored** (machine-local). Structure and conventions live in
  `wiki/CLAUDE.md`. claude-mem records *what happened*; the wiki records *what the
  code is*.

Keep the wiki current as you learn something durable about a codebase — ingest a
source or update the relevant note. Capture the non-obvious and the *why*; skip
routine edits and plain restatements of the code.

## Working on workspace repos: git worktrees

Repos are mirrored under `workspace/<group>/…/<repo>` by `/clone-repos`. To work
on one, **do it in a git worktree**, not on the clone's main checkout:

- Use the built-in worktree support (`EnterWorktree`) or the
  `superpowers:using-git-worktrees` skill to create an isolated worktree + branch
  off the target repo.
- Make changes there, run tests, then open an MR / merge, and remove the worktree
  when done.
- This keeps the pristine `workspace/` clones clean (so `/clone-repos` can always
  fast-forward them) and isolates parallel work.

## Folders

- **`workspace/`** — mirrored clones of the workspace repos (git-ignored).
- **`wiki/`** — the curated Obsidian long-term-memory vault (git-ignored).
- **`workflows/`** — full `uv run` Python scripts. All inputs via `args`.
- **`.claude/skills/`** — thin launchers that invoke a workflow.
- **`config/`** — holds `hub.config.yaml` (git-ignored). Currently **vestigial**:
  the remaining `clone-repos` skill hardcodes its own group list, so nothing reads
  this file today. Kept for future config-driven skills.
- **`playground/`** — disposable / random scripts (git-ignored).
- **`data/`** — generated outputs (git-ignored).

## Skills

- **`/clone-repos`** — mirrors every GitLab project under the configured
  `skillcorner` groups to `./workspace/<group>/…/<repo>`. Clones missing repos,
  fast-forwards existing clean ones onto their default branch, and **skips any
  repo with uncommitted changes**. Reads `GITLAB_TOKEN` from the environment (a
  `read_api` + `read_repository` PAT); never stores it. Groups/destination are
  hardcoded in `workflows/clone_repos.py`. Run `--dry-run` for a preview.

## Conventions

- The tracked Markdown is `README.md` and `CLAUDE.md`. The `wiki/` vault and
  `workspace/` clones are git-ignored (maintained locally per machine).
- **Secrets:** connector *auth* lives in the Claude app / MCP connectors, never in
  this repo. `GITLAB_TOKEN` comes from the environment (see `.claude/hub-env`).
- **Connector availability:** MCP connectors are present in cloud routines but may
  be absent in local runs.
  
  
