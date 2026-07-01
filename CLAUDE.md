# CLAUDE.md — Claude Ops Hub

This repo is a **project-agnostic control layer for Claude Code**, not an app.
It wires together capabilities Claude Code already ships (claude-mem, the
Obsidian vault, MCP connectors, `Workflow`/`Agent`) and adds only the glue.
Read `README.md` for the full rationale.

## The one rule

**Everything project-specific lives in `config/hub.config.yaml`** (git-ignored).
There is exactly one config file — no template, no example. It is created for
you by the `/setup-config` skill. Do not hardcode an org, project, group, or
channel anywhere else; workflows and skills read the config.

## Language

**All scripting is Python, run via `uv`** (`uv run ...`), with dependencies
declared inline via PEP 723 headers — no venv, no `pyproject.toml`, no committed
Python package.

## Where code goes

- **One-liner → a skill.** If the logic is a short inline snippet (e.g. read
  `config/hub.config.yaml` and emit JSON), put it directly in the skill as a
  `uv run --with pyyaml python - <<'PY' ...` block.
- **More than a one-liner → `workflows/`.** Anything substantial is a committed
  script under `workflows/` — either a `Workflow` `.js` orchestration script or a
  `uv run` Python script. Skills stay thin: they read config inline (if needed),
  then launch the workflow.

Workflow `.js` scripts cannot read the filesystem, so all config-reading happens
in the launching skill, never in the workflow.

## Memory: two layers, no overlap

- **claude-mem** = automatic "what I did." Captured every session, re-injected
  at `SessionStart`. Zero effort. Local SQLite + Chroma.
- **Obsidian vault (`vault/`)** = curated "what I decided / learned" **about the
  codebase in this workspace** (this repo is the main working directory). A
  browsable knowledge graph in **zettelkasten** mode: atomic notes, linked with
  `[[wikilinks]]`, no folder hierarchy. This is where durable codebase knowledge
  lives — architecture decisions, non-obvious mechanisms, gotchas, why something
  is the way it is. Powered by the `claude-obsidian` plugin skills (see below).
  Open `vault/` in the Obsidian app for the graph view. Don't add a third store.

**Use the vault automatically — no need to be asked:**

- **Read before you explore.** Before diving into an unfamiliar part of the
  codebase, run **`/wiki-query`** (or ask "what do you know about X?") to pull
  what's already curated. Cite the vault pages, not guesses.
- **Write after meaningful learning.** Once you learn something durable about
  the codebase — a design decision, a non-obvious mechanism, a gotcha — capture
  it with **`/save`** (a conversation/insight) or **`ingest`** (a source file
  or doc). Do **not** save routine edits, restatements of the code, or
  conversation-only trivia.
- **Keep it healthy.** Occasionally run **`lint the wiki`** to surface orphans,
  dead links, and stale claims; run **`/autoresearch`** only when you genuinely
  need multi-source external research filed into the vault.

## Folders

- **`config/`** — the single `hub.config.yaml`. Nothing else.
- **`workflows/`** — full scripts (`Workflow` `.js` orchestration, or `uv run`
  Python). All inputs via `args`.
- **`.claude/skills/`** — thin launchers: read config inline (uv+pyyaml) if
  needed, then invoke the matching workflow.
- **`docs/`** — HTML documentation, only when a workflow is genuinely hard to
  follow. Open in a browser.
- **`playground/`** — disposable / random scripts (git-ignored).
- **`data/`** — generated HTML outputs (git-ignored).
- **`vault/`** — the Obsidian knowledge graph.

## Skills

- **`/setup-config`** — interactive: asks for project name + which connectors to
  enable, then runs `workflows/setup_config.py` to write and validate
  `config/hub.config.yaml`.
- **`/daily-brief`** — reads config inline, fans out over enabled connectors,
  writes one HTML digest to `data/digest-<date>.html`.

**`claude-obsidian` skills — codebase memory (use automatically):**

| Skill / trigger | Use when |
|---|---|
| **`/wiki-query`** ("what do you know about X?") | Before exploring an unfamiliar area — pull curated codebase knowledge first. |
| **`/save`** ("save this") | After a session or discussion yields a durable decision/insight worth keeping. |
| **`ingest [file]`** | To file a source doc, design note, or spec into the vault as linked pages. |
| **`lint the wiki`** | Periodic health check — orphans, dead links, stale claims. |
| **`/autoresearch [topic]`** | Only when multi-source external research needs to be filed into the vault. |
| **`/wiki`** | First-run vault setup, or to continue where you left off. |

## Conventions

- Generated outputs and docs are HTML. `README.md` and this file are the only
  tracked markdown.
- **Secrets:** connector *auth* lives in the Claude app / MCP connectors, never
  in this repo. `hub.config.yaml` holds only non-secret selectors and is
  git-ignored.
- **Connector availability:** MCP connectors are present in cloud routines but
  may be absent in local runs. Schedule connector-only jobs as `cloud`.
