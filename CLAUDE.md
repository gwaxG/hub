# CLAUDE.md — Claude Ops Hub

This repo is a **project-agnostic control layer for Claude Code**, not an app.
It wires together capabilities Claude Code already ships (claude-mem, MCP
connectors, the `Agent` tool) and adds only the glue.
Read `README.md` for the full rationale.

## The one rule

**Everything project-specific lives in `config/hub.config.yaml`** (git-ignored).
There is exactly one config file — no template, no example. It is created for
you by the `/setup-config` skill. Do not hardcode an org, project, group, or
channel anywhere else; workflows and skills read the config.

## Language

**All scripting is Python, run via `uv`** (`uv run ...`), with dependencies
declared inline via PEP 723 headers — no venv, no `pyproject.toml`, no committed
Python package. **No JavaScript.** Committed workflow scripts are Python only;
do not add `Workflow` `.js` orchestration scripts. LLM fan-out (analyzing many
repos, etc.) is done by dispatching the **Agent tool** from the launching skill,
while the committed Python script owns the deterministic work (discovery, file
I/O, indexing). (The legacy `daily-brief.workflow.js` predates this rule.)

## Where code goes

- **One-liner → a skill.** If the logic is a short inline snippet (e.g. read
  `config/hub.config.yaml` and emit JSON), put it directly in the skill as a
  `uv run --with pyyaml python - <<'PY' ...` block.
- **More than a one-liner → `workflows/`.** Anything substantial is a committed
  **Python** script under `workflows/` (`uv run`). Skills stay thin: they read
  config inline (if needed), run the Python script for deterministic work, and
  dispatch Agent subagents for any LLM work.

## Memory: two layers, no overlap

- **claude-mem** = automatic "what I did." Captured every session, re-injected
  at `SessionStart`. Zero effort. Local SQLite + Chroma.
- **`docs/`** = curated "what I've learned about the code" — a **living Markdown
  knowledge base Claude maintains as it works**, graph-like and cross-linked:
  - **Per-project notes** at `docs/workspace_graph/<group>/<repo>.md` — purpose,
    tech stack, architecture & key components, entry points, gotchas, and
    `## Cross-references` to related repos (relative-path Markdown links, so the
    set reads as a graph). `docs/workspace_graph/index.md` is the overview.
  - **ADRs** at `docs/adr/NNNN-title.md` — architecture decisions: context,
    decision, consequences.

**Keep `docs/` current as you learn — no need to be asked:**

- **Read before you explore.** Before diving into an unfamiliar project, read its
  `docs/workspace_graph/…` note and any relevant ADR. Cite them, not guesses.
- **Write/update after meaningful learning.** When you learn something durable —
  how a project works, its structure, a design decision, a non-obvious mechanism,
  a gotcha — update that project's note and link the related repos. **If a project
  has no note yet, read the project and write one describing how it works and its
  structure** (the `/explain-repo` skill does exactly this).
- **Record decisions as ADRs.** When a design/architecture decision is made or
  discovered, add or update an ADR under `docs/adr/`. **If an ADR that should
  exist is missing, investigate the project and write it.**
- Capture the non-obvious and the *why*; do **not** record routine edits or plain
  restatements of the code.

## Folders

- **`config/`** — the single `hub.config.yaml`. Nothing else.
- **`workflows/`** — full scripts (`Workflow` `.js` orchestration, or `uv run`
  Python). All inputs via `args`.
- **`.claude/skills/`** — thin launchers: read config inline (uv+pyyaml) if
  needed, then invoke the matching workflow.
- **`docs/`** — the living Markdown knowledge base Claude maintains: per-project
  notes under `docs/workspace_graph/` (a cross-linked graph) and ADRs under
  `docs/adr/`. May also hold the occasional HTML page for a hard-to-follow workflow.
- **`playground/`** — disposable / random scripts (git-ignored).
- **`data/`** — generated HTML outputs, e.g. digests (git-ignored).

## Skills

- **`/setup-config`** — interactive: asks for project name + which connectors to
  enable, then runs `workflows/setup_config.py` to write and validate
  `config/hub.config.yaml`.
- **`/daily-brief`** — reads config inline, fans out over enabled connectors,
  writes one HTML digest to `data/digest-<date>.html`.
- **`/explain-repo`** — documents cloned `workspace/` repos into the `docs/`
  knowledge base: runs `workflows/explain_repo.py` to discover repos + build the
  index, and dispatches an Agent per repo to write a cross-linked Markdown note
  under `docs/workspace_graph/` (mirroring the workspace tree). Use it to create a
  project's note when one is missing.
- **`/changelog`** — watches what changed across `workspace/` repos since the last
  run: runs `workflows/changelog.py plan` to diff every repo against a persisted
  per-repo commit-SHA snapshot (`data/changelog_state.json`), dispatches an Agent
  per changed repo to classify the change (routine/notable/architectural) and
  update its `docs/workspace_graph` note (notable+) or draft an ADR under
  `docs/adr/` (architectural), then `changelog.py record` appends a dated section
  to the root `CHANGELOG.md` and advances the snapshot. Run after `/clone-repos`.

## Conventions

- The `docs/` knowledge base is **Markdown** (per-project notes + ADRs), so it
  reads as a cross-linked graph and stays diff-friendly. `README.md`, `CLAUDE.md`,
  and everything under `docs/` are the tracked Markdown. Other generated outputs
  (e.g. digests) are HTML written to `data/` (git-ignored).
- **Secrets:** connector *auth* lives in the Claude app / MCP connectors, never
  in this repo. `hub.config.yaml` holds only non-secret selectors and is
  git-ignored.
- **Connector availability:** MCP connectors are present in cloud routines but
  may be absent in local runs. Schedule connector-only jobs as `cloud`.
