---
name: explain-repo
description: Analyze a workspace repo (or a whole group subtree) and write a cross-linked Markdown note per repo into the docs/ knowledge base (docs/workspace_graph/), mirroring the workspace tree, plus an index overview. Use when the user wants generated documentation of the cloned skillcorner repos, asks to "explain"/"document" a repo, or when a project has no docs/ note yet.
---

# explain-repo

Documents repos cloned under `workspace/` (by `/clone-repos`). The hub is
Python-only, so the split is:

- **`workflows/explain_repo.py`** (deterministic) — discovers repos, pre-creates
  the mirrored doc dirs, and builds `index.md`.
- **You (the skill)** dispatch an **Agent per repo** to read it and write its
  markdown doc. No JavaScript / Workflow scripts.

Each repo → one doc at the mirrored path `docs/workspace_graph/<group>/<repo>.md`.

- **Single repo** → pass its path → one doc.
- **A group dir** (e.g. `skillcorner/software`) → every repo under it.
- **No arg** → ask which repo/subtree first (don't silently document all 256 — a
  heavy run dominated by the ~120 Python repos).

Re-runs are idempotent: repos whose doc already exists are **skipped** unless the
user says "regenerate"/"force".

## Steps

1. **Plan the run.** `TARGET` is the path the user named, relative to `workspace/`
   (empty = the whole workspace, only after confirmation). Add `--force` to
   regenerate existing docs.
   ```bash
   uv run workflows/explain_repo.py plan "skillcorner/software/skcr-utils"
   ```
   This prints JSON: `{generated, docsRoot, indexPath, repos:[{name, group,
   relPath, repoPath, docPath}], skipped:[...]}` and pre-creates the mirror dirs.
   Report to-analyze vs skipped counts. If `repos` is empty (all skipped), tell
   the user and offer `--force`. If the JSON has `error`, stop and surface it.

2. **Analyze each repo with a subagent.** For every entry in `repos`, dispatch a
   `general-purpose` Agent (run independent repos in parallel — multiple Agent
   calls in one message; for a large group, batch ~8–10 at a time). Give each
   agent the repo's `repoPath`, `docPath`, `group`, `relPath`, and `generated`,
   with this instruction:

   > Document one git repository for a reference wiki. **Do not modify the repo.**
   > Inspect `<repoPath>`: read the README, the top-level tree, dependency
   > manifests that exist (pyproject.toml / requirements*.txt / package.json /
   > Chart.yaml / Dockerfile / *.tf), and 2–5 key source/entrypoint files you
   > judge most revealing. Detect the primary language and repo type (python-
   > service / helm-manifests / library / js-app / empty).
   > Then **write a markdown file to exactly `<docPath>`** with this structure,
   > filling every `<...>` from what you observed (concise, concrete, no filler),
   > keeping the frontmatter keys and headings verbatim:
   > ```markdown
   > ---
   > type: source
   > title: <group>/<name>
   > repo: workspace/<relPath>
   > generated: <generated>
   > language: <primary-language>
   > tags: [repo, <group tokens comma-separated>, <primary-language>]
   > ---
   > # <name>
   >
   > > [!info] <group> · <primary-language> · <repo-type>
   >
   > ## Purpose
   > ## Tech stack
   > ## Architecture & key components
   > ## Entry points & how to run
   > ## Dependencies
   > ## Gotchas / notes
   > ## Cross-references
   > ```
   > If the repo is empty (nothing tracked outside `.git`), write a one-line stub
   > saying so. Reply with the doc path once written.

   (For a single repo you may just do this inline yourself instead of spawning an
   agent.) The `language:` frontmatter and a filled `## Purpose` matter — the
   index is built from them.

3. **Build the index.**
   ```bash
   uv run workflows/explain_repo.py index
   ```
   Regenerates `docs/workspace_graph/index.md` (grouped table of every documented
   repo → language + one-line purpose, linked). Safe to run anytime.

4. **Report** how many docs were written/skipped/failed and the index path; offer
   to open `docs/workspace_graph/index.md`.

## Notes

- **The docs ARE the knowledge base.** `docs/workspace_graph/` is the living,
  cross-linked Markdown graph Claude maintains (see CLAUDE.md "Memory"). Keep each
  note's `## Cross-references` pointing at related repos so the set reads as a graph.
- **Markdown, not HTML** — the knowledge base is Markdown (diff-friendly, linkable).
- **Python only, no JS:** the committed script is `explain_repo.py`; LLM work is
  Agent dispatch from this skill.
- **Cost:** whole-workspace runs (256 repos) are heavy; scope to a repo or group
  unless the user explicitly wants everything.
- **Idempotent:** existing docs are skipped; pass `--force` in step 1 to redo.
- **Stays inside the hub:** writes only under `docs/workspace_graph/`. Never
  outside the repo.
