---
name: hub-graph
description: Build a code-graph report for a Python repo — import graph, dependency matrix, layer coupling, cycles, complexity, and churn x complexity hotspots — as one self-contained HTML page. Use when the user wants to explore a codebase as a graph, see code metrics, find hotspots or god-modules, or check whether a repo's layering actually holds.
---

# hub-graph

Runs `workflows/code_graph.py` against a repository and then **reads the result
for the user**. The script is deterministic (grimp + radon + git, no LLM); your
job is to launch it with the right arguments and interpret what comes back.

This is the **whole-repo** view — "what does this codebase look like". For "how
does this branch's feature integrate into it", use the `hub-mr` skill, which
diffs two revisions and returns a verdict. Both share
`workflows/codegraph_core.py`, `templates/_shared.css` and `templates/_shared.js`.

The analysis is strictly read-only: grimp's on-disk cache is disabled and the
report is written to `tmp/code-graph/` inside the hub — `hub/tmp` is where
generated artefacts live and is gitignored — never into the analysed repo.

## Output

`tmp/code-graph/<repo>.html` — one self-contained page, no CDN, no
network, opens straight from disk:

| Section | What it answers |
|---|---|
| Summary cards | size, cycles, median instability/MI, bus-factor-1 count |
| Dependency graph | force-directed; node size = LOC, colour = layer, arrows importer → imported |
| Dependency matrix | topologically ordered, so every normal import sits **above** the diagonal — amber below it = a back-edge |
| Layer coupling | layer → layer import counts; the matrix an `import-linter` contract would police |
| Dependency cycles | Tarjan SCCs — the parts that cannot be understood or extracted alone |
| Node metrics | sortable/filterable: LOC, Ca, Ce, I, A, dist, CC, MI, commits, churn, authors |
| Hotspots | per-file normalised **churn × complexity** + scatter |

`tmp/code-graph/<repo>.json` holds the same data — use it when the user
asks a question the page doesn't answer directly, rather than re-running.

## Metrics, and what they mean

- **Ca / Ce** — fan-in / fan-out.
- **I** = Ce/(Ca+Ce) — instability. 0 = nothing depends on anything (stable), 1 = pure consumer.
- **A** — abstractness: classes inheriting ABC/Protocol or carrying `@abstractmethod`, over all classes.
- **dist** = |A + I − 1| — distance from Martin's main sequence. High means either
  *concrete and heavily depended upon* (painful to change) or *abstract and unused*.
- **CC** — worst cyclomatic complexity in the node (>10 warrants a look, >20 is a problem).
- **MI** — radon maintainability index; below 65 is poor.
- **churn** — lines added + deleted in the history window; **authors** = 1 is bus factor 1.
- **hotspot score** — normalised churn × complexity. Complexity only costs you
  where the code keeps changing, so this ranks where review and test effort pays off.

## Steps

1. **Pick the repo.** Prefer a `workspace/` mirror. Nothing needs installing —
   the script is a PEP 723 script with inline dependencies.

   ```bash
   uv run workflows/code_graph.py workspace/skillcorner/software/football-metadata-service
   ```

2. **Check the packages line in the output.** This is the one thing that
   silently goes wrong. The script prints the resolved `root` and `packages`; if
   it warns that imports are implausibly few for the module count, the sys.path
   root is wrong — pass `--root`:

   ```bash
   uv run workflows/code_graph.py workspace/skillcorner/software/wilson --root server
   ```

   Django repos are auto-detected via `manage.py` (wilson resolves to
   `root=server/`, packages `api, app, son, wilson, …`). Analysing `server`
   itself as the package would resolve every intra-project import as external
   and yield an almost edgeless graph.

3. **Interpret the report for the user** — don't just hand over a path. Name the
   god-modules (highest Ca), the cycles, the worst hotspots, and any layer pair
   with imports running both ways. Tie findings to something actionable: an
   `import-linter` contract for the layer violations, a test or extraction for a
   hotspot, a seam for a cycle.

4. **Offer the page.** Give the `file://` path, and offer to open it (`xdg-open`)
   or to publish it as an Artifact if they want to share it.

## Options

| Flag | Default | Notes |
|---|---|---|
| `--root DIR` | auto | directory placed on sys.path (see step 2) |
| `--package NAME` | auto | repeatable; overrides discovery entirely |
| `--level module\|package\|auto` | `auto` | `package` above 150 modules, else `module` |
| `--depth N` | 2 | dotted segments per node at package level (`son.models`); 3 for a finer wilson view |
| `--since` | `1 year ago` | git history window for churn/authors |
| `--exclude STR` | `migrations`, `alembic.versions`, `node_modules` | repeatable; drops modules whose path contains STR |
| `--out DIR` | `tmp/code-graph` | report directory |

Layers are always one segment coarser than nodes, so the layer matrix stays
informative; when they would coincide the page hides that section.

## Notes

- **Runtime** scales with repo size and history: ~5s for a small service, ~90s
  for wilson (630 modules). Most of it is radon + the git log walk.
- **Only Python imports.** No call graph, no runtime coupling, no JS/TS — a
  module that only talks to another through Django signals, a queue, or an HTTP
  call shows up as unconnected. Say so when it matters (e.g. wilson's lambdas).
- **`--level package` aggregates**: `cc_max` is the worst file in the package,
  `MI` is the mean, `commits` counts distinct commits touching any member.
- **Branch-sensitive, not diff-scoped**: it analyses the working tree as checked
  out, and every section covers the whole repo. `--since` bounds only the
  churn/authors window. Use `hub-mr` for a change-scoped evaluation.
- Adjacent tools, when the graph isn't enough: `import-linter` (turn the layer
  matrix into a CI gate), `pydeps` (quick picture), `understand-anything:understand`
  (narrated graph + dashboard), Joern (taint/reachability).
