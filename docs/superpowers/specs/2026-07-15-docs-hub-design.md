# Claude Ops Hub — curated `docs/` vault, hooks & documentation skills

**Date:** 2026-07-15
**Status:** approved, in implementation

## Goal

Turn the hub into a project-agnostic control layer whose Layer-2 memory is a
**curated, tracked `docs/` vault** describing the workspace repos, kept in sync
with source via a **reconciliation queue**, enforced by **fast deterministic
hooks**, and maintained by **thin skills over Python workflows**.

## Decisions (locked)

- **Full build** — vault + 6 hooks + 8 workflows + 6 skills + tests.
- **Hand-rolled `docs/`** — retire `wiki/` / claude-obsidian from the hub's
  memory story. `docs/` is plain Markdown maintained by hub hooks/workflows/skills.
- **`docs/` is tracked** in git, **except** `docs/generated/**` and
  `docs/memory/**` (reproducible/bookkeeping — git-ignored).
- **Machinery + scaffold only** this pass — no real repo ingestion yet.
- **pytest** for the deterministic `hub_lib` core.
- **Root `pyproject.toml`** manages shared deps + dev/test env; `hub_lib/` is a
  normal importable module. **Hooks are stdlib-only**, run via `uv run --no-project`
  so they never pay dependency-resolution cost. Workflows use the project env and
  may additionally carry PEP 723 headers for standalone portability.

## Layout

```
hub/
├── CLAUDE.md            # rewritten to this spec
├── README.md            # reconciled: docs/ replaces wiki/, git policy stated
├── pyproject.toml       # shared deps (pytest, pyyaml, requests) + hub_lib module
├── hub_lib/             # stdlib-only pure logic (queue, frontmatter, paths, classify)
├── .claude/
│   ├── settings.json    # wires the 6 hooks
│   ├── hooks/           # session_start, classify_prompt, protect_docs,
│   │                    # track_doc_impact, validate_docs, session_end
│   └── skills/          # clone-repos + 6 new
├── workflows/           # clone_repos.py + 8 new
├── docs/                # tracked curated vault (generated/ + memory/ ignored)
└── tests/               # pytest over hub_lib
```

## `docs/` vault taxonomy

`graph/` `architecture/decisions/` `domain/` `workflows/` `runbooks/`
`interfaces/` `operations/` `development/` `generated/` `memory/` — each seeded
with a `README.md` and front-matter template; top-level `docs/README.md` holds
the vault index + git policy.

**Front-matter fields:** `title, type, status, owners, systems, source_paths,
related, last_verified, generated`.

`docs/generated/` files carry a banner (generating workflow, UTC timestamp,
source paths, complete|partial). `docs/memory/` holds `pending-updates.jsonl`,
`stale-docs.json`, `last-validation.json`.

## `hub_lib/` (shared, stdlib-only)

- `queue.py` — append / dedup / list / resolve on `pending-updates.jsonl`
- `frontmatter.py` — minimal YAML-subset parser for the fixed field set
- `paths.py` — hub-root, workspace-mirror, worktree detection; source→doc mapping
- `classify.py` — deterministic keyword prompt classifier

## Hooks (stdlib-only, `uv run --no-project`)

| Hook | Event | Responsibility |
|------|-------|----------------|
| `session_start.py` | SessionStart | Inject compact context: policy line, vault index, stale warnings, unresolved-queue count. Never dumps the vault; no claude-mem duplication. |
| `classify_prompt.py` | UserPromptSubmit | Deterministic keyword → task category; point at the relevant `docs/` folder. |
| `protect_docs.py` | PreToolUse (Edit\|Write\|Bash) | Deny: edits to `docs/generated/**`; writes into the `workspace/` mirror; unsafe git against a mirror; reads of `.claude/hub-env`. |
| `track_doc_impact.py` | PostToolUse (Edit\|Write) | If path under `workspace/`, append one queue record. No LLM, no doc writes. |
| `validate_docs.py` | Stop | Cheap checks + unresolved-impact reminder. Report-only (no recursive writes). |
| `session_end.py` | SessionEnd | Persist unresolved warnings, refresh cheap indexes, write `last-validation.json`. No episodic duplication. |

## Reconciliation queue

Buffer between cheap deterministic *detection* (PostToolUse appends a JSONL
record on `workspace/` edits) and deliberate semantic *update*
(`/update-project-docs` dedups, inspects the **final git diff**, maps source→doc
via front-matter, classifies impact, regenerates `generated/`, updates curated
docs only when behavior is established, validates, then removes resolved lines).
The `Stop` hook surfaces a non-empty queue so drift is visible, never silent.

Record shape:
```json
{"ts":"…","event":"source_edit","source_path":"workspace/…/x.py","tool":"Edit","candidate_docs":["docs/…"],"resolved":false}
```

## Workflows (Python, project env; PEP 723 optional)

`scaffold_docs.py` · `source_map.py` · `validate_docs.py` · `update_project_docs.py`
· `ingest_repository.py` · `refresh_graph.py` · `new_adr.py` · `find_knowledge.py`.
Each owns deterministic discovery/mapping/validation/I-O; semantic writing is the
skill's Agent step.

## Skills (thin launchers)

`/update-project-docs` `/validate-docs` `/ingest-repository` `/create-adr`
`/refresh-project-graph` `/find-project-knowledge` — derive args → run workflow →
dispatch `Agent` for semantic work → summarize.

## Testing

`tests/` (pytest via the project env) over `hub_lib` pure functions: queue
append/dedup/resolve, front-matter parse, source→doc mapping, prompt
classification, validation checks.

## Build order

1. Foundation — pyproject, `hub_lib` + tests, `scaffold_docs.py` + run, gitignore,
   `CLAUDE.md`, `README.md`.
2. Hooks — 6 hooks + `settings.json`.
3. Workflows + skills.
4. Validation pass — `/validate-docs` on the empty-but-valid vault; hooks fire clean.
