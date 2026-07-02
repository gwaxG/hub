# Claude Ops Hub

A **project-agnostic** home for driving Claude Code as a personal engineering
assistant: long-term memory, multi-agent workflows, scheduled monitoring, and
phone access — built almost entirely from Claude Code plugins and connectors
rather than a bespoke backend service.

Nothing in this repo is tied to a particular company or project. Everything
project-specific lives in **one file**: `config/hub.config.yaml`, created for
you by the `/setup-config` skill. Swap that file and the hub serves a different
project.

---

## Why this shape (the approach)

The common instinct — a custom FastAPI + Celery + Postgres + pgvector + bot
service — duplicates capabilities Claude Code already ships. This hub instead
**wires together what already exists** and adds only the missing glue:

| Need | What provides it | This hub adds |
|------|------------------|---------------|
| Long-term memory | `claude-mem` plugin (SQLite + local Chroma vectors) | a curated Markdown knowledge base in `docs/` on top |
| Semantic recall | `claude-mem` (local `all-MiniLM-L6-v2` embeddings) | nothing — already local |
| Tool access (Sentry/GitLab/Notion/Slack) | claude.ai MCP connectors | config-driven workflows |
| Multi-agent orchestration | `superpowers` + `Agent`/`Workflow` tools | saved workflow scripts |
| Scheduling | cloud routines + local cron/`/loop` | schedule definitions |
| Phone access | claude.ai app + Claude Code channels | setup notes |

**No extra database.** `claude-mem` already runs SQLite+FTS5 for structured/
keyword search *and* a local ChromaDB for semantic vectors — adding sqlite-vec
or a vector-memory MCP would duplicate it. (If Chroma's RAM use bites, switch
`claude-mem` to SQLite-only mode.)

---

## Layout

```
hub/
├── README.md          # this file
├── CLAUDE.md          # how the pieces connect
├── config/            # the ONE file: hub.config.yaml (git-ignored)
├── workflows/         # full scripts: uv-run Python (no JS)
├── .claude/skills/    # thin launchers (/setup-config, /daily-brief, /explain-repo)
├── docs/              # the living Markdown knowledge base (per-project notes + ADRs)
├── data/              # generated HTML outputs, e.g. digests (git-ignored)
└── playground/        # disposable/random scripts (git-ignored)
```

All scripting is **Python via `uv`** (inline PEP 723 deps — no venv, no JS). A
short one-liner lives inline in a skill; anything larger is a committed Python
script in `workflows/`.

The `docs/` knowledge base is **Markdown** (cross-linked notes + ADRs, kept
current by Claude). Other generated outputs (e.g. digests) are HTML in `data/`.

---

## The layered-memory model

Two systems, clear division of labor — don't duplicate between them:

- **`claude-mem` = automatic "what I did."** Captures observations every
  session and injects relevant context at the next `SessionStart`. Zero effort.
  Backed locally by SQLite (keyword) + Chroma (semantic).
- **`docs/` = curated "what I've learned about the code."** A living, cross-linked
  **Markdown knowledge base Claude maintains as it works**: one note per project
  under `docs/workspace_graph/<group>/<repo>.md` (purpose, tech stack, architecture,
  entry points, gotchas, `## Cross-references` to related repos), plus Architecture
  Decision Records under `docs/adr/`.

The rule (see `CLAUDE.md`): **read the relevant note before exploring a project;
update it — or write it if missing — after you learn something durable; record
design decisions as ADRs.** Use `/explain-repo <target>` to generate a project's
note when one doesn't exist yet. No app or plugin required — it's plain Markdown
you can read on GitHub or in any editor.

---

## Workflows & agents

- **Ad-hoc parallel work:** the `Agent` tool with a fitting subagent type
  (`Explore`, `Plan`, `code-reviewer`, …).
- **Repeatable fan-out:** `Workflow` scripts in `workflows/`. Each reads
  `config/hub.config.yaml` so it stays project-agnostic. Starters:
  - `daily-brief` — Sentry regressions + GitLab failed pipelines/stale MRs +
    Notion changes → one HTML digest in `data/digest-<date>.html`.
  - `incident-triage`, `mr-review` — generic, config-driven.
- **Isolation:** use git worktrees (`EnterWorktree`, the
  `superpowers:using-git-worktrees` skill, or `isolation:"worktree"` inside a
  workflow) when several agents edit files in parallel.

---

## Scheduling (hybrid)

Rule of thumb: **needs only APIs → cloud; needs your local files → local.**

- **Cloud routines** (`/schedule`) run even when your laptop is off and push
  notifications to your phone — ideal for the monitoring jobs.
- **Local** `cron` / the `/loop` skill for jobs that need a checked-out repo.

Schedules are declared in `config/hub.config.yaml` under `schedules:`.

---

## Phone access

- **claude.ai mobile app** — authenticate the Sentry/GitLab/Notion/Slack
  connectors there; this is where digests and routine notifications land.
- **Claude Code channels** — already enabled (`channelsEnabled: true`). To drive
  local sessions from your phone, set `remote_control_at_startup: true` in
  `~/.claude/policy-limits.json` (confirm the in-app toggle first — it widens
  remote access to your machine).

---

## Make it yours

Run the setup skill — it interviews you and writes the single config file:

```
/setup-config
```

It asks for the project name and which connectors to enable, then writes and
validates `config/hub.config.yaml` (via `uv run workflows/setup_config.py`).
That's the only file that carries project specifics. It's git-ignored — keep
selectors there, never in committed files or global `CLAUDE.md`. Connector
*auth* lives in the Claude app / MCP connectors, not in any file here.

Then run `/daily-brief` for the morning digest.
