---
title: 0001 — Adopt curated docs vault with reconciliation queue
type: decision
status: current
owners: []
systems: []
source_paths:
  - CLAUDE.md
  - hub_lib/queue.py
  - .claude/hooks/track_doc_impact.py
  - workflows/update_project_docs.py
related:
  - ../../README.md
last_verified: 2026-07-15
generated: false
---

# 0001 — Adopt curated docs vault with reconciliation queue

## Context

The hub needs a Layer-2 "what the code is and why" memory to complement
`claude-mem`'s episodic "what I did." That knowledge must stay trustworthy as the
workspace repos change constantly. Naively regenerating docs on every source edit
is wrong: a single edit may be incomplete, experimental, reverted or
behavior-preserving, and rewriting docs well needs semantic effort that hooks
(which must be fast and non-recursive) cannot do.

## Decision

Maintain a hand-rolled, git-tracked `docs/` vault with a fixed taxonomy and YAML
front matter. Decouple *detecting* documentation impact from *updating* docs via a
reconciliation queue (`docs/memory/pending-updates.jsonl`):

- a PostToolUse hook appends one record when a `workspace/` file is edited
  (cheap, deterministic, no LLM);
- `/hub-update-project-docs` later dedups, inspects the **final** git diff, maps
  source→doc, classifies impact, regenerates `docs/generated/`, updates curated
  docs **only when behavior is established**, validates, and clears resolved records.

Hooks detect + enforce; skills/agents reason; Python workflows own I/O.

## Alternatives considered

- **Custom service (FastAPI + Postgres + pgvector).** Rejected: duplicates
  `claude-mem`'s local SQLite + Chroma and adds operational weight for a
  single-user hub.
- **Reuse the `claude-obsidian` wiki plugin.** Rejected for the hub's own layer:
  we want deterministic, testable Python glue and a plain tracked vault, not a
  plugin-managed Obsidian vault.
- **Rewrite docs synchronously on every edit.** Rejected: documents noise,
  thrashes on reverts, needs an LLM in the hot path, and risks hook recursion.

## Consequences

- Curated knowledge is shared, reviewable and backed up in git; `docs/generated/`
  and `docs/memory/` stay machine-local (git-ignored) as reproducible bookkeeping.
- Doc updates are deliberate and gated on established behavior, so the vault avoids
  documenting speculative work — at the cost of not being instantaneously current
  until `/hub-update-project-docs` runs.
- Requires the reconciliation discipline to actually be run; the `Stop` hook
  surfaces a non-empty queue so drift stays visible.

## Status

Current.
