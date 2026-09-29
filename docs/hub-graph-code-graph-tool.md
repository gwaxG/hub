# hub-graph / hub-mr — code graph & integration reports

Two skills over one engine, both producing a self-contained HTML report in
`hub/tmp/code-graph/`:

- **`hub-graph`** → `workflows/code_graph.py` — whole-repo snapshot: import
  graph, dependency matrix, layer coupling, cycles, per-node metrics, and
  churn × complexity hotspots. Answers "what does this codebase look like".
- **`hub-mr`** → `workflows/mr_graph.py` — analyses the repo at the merge base
  *and* at the branch head, then reports the difference: where the feature sits,
  whether repo-level metrics slid, and eight named integration checks with a
  `clean` / `watch` / `regression` verdict. Answers "how does this feature
  integrate".

- **Engine:** `grimp` (import graph) + `radon` (LOC/CC/MI) + `ast` (abstractness)
  + `git log --numstat` (churn, authors). No LLM, fully deterministic, offline.
- **Template:** `workflows/templates/code_graph.html` — four `{{PLACEHOLDER}}`
  tokens filled by `str.replace`; all CSS/JS inline, no CDN, canvas-rendered
  visuals. SkillCorner palette (dark green gradient, neon-green accents).
- **Artefacts:** `hub/tmp/code-graph/<repo>.{html,json}`. `hub/tmp` is the hub's
  generated-artefact folder and is gitignored (`tmp/*`, `!tmp/.gitkeep`).
- **Read-only:** `grimp.build_graph(..., cache_dir=None)` — without that grimp
  writes a cache into the analysed repo, which would dirty a `workspace/` mirror.

## Shared layer

`workflows/codegraph_core.py` is a plain module, not a script — both CLIs run
under `uv run` with the same PEP 723 dependency set, and Python puts the script's
own directory on `sys.path`, so `import codegraph_core` resolves with no
packaging (the hub stays `package = false`). It owns discovery, the graph build,
metrics, git history, SCC/topological ordering, `analyse()`, `snapshot()` and
`render()`.

Templates share `templates/_shared.css` and `templates/_shared.js` through the
`STYLE` and `HELPERS` tokens. `_shared.js` carries `createForceGraph` and
`createMatrix` as factories parameterised by colour/tooltip callbacks, so both
reports draw the same geometry with different meaning. `render()` raises if any
`{{TOKEN}}` survives — which caught the partials describing their own tokens in
their header comments.

## hub-mr specifics

- **Snapshots via `git archive`**, not `git worktree` / `git checkout`: it touches
  neither the mirror's working tree nor its `.git`, so an interrupted run cannot
  leave a repo dirty or half-switched. Trees land in
  `tmp/code-graph/.snapshots/` and are removed unless `--keep-snapshots`.
- **History still comes from the real repo**, rev-limited (`git log <rev>`), so a
  base snapshot is scored on the history it actually had.
- **Comparability is forced**: base is analysed with the head's resolved level,
  depth and sys.path root. Without that the two payloads describe different
  pictures and every delta is noise.
- **Verdict is derived from checks, not a composite score** — a made-up number
  would hide which finding mattered. `--fail-on warn|fail` gives a CI gate.
- Checks: new cycles (fail), new two-way layer pairs (fail), new layer coupling
  (warn), Stable Dependencies Principle (warn), complexity budget (warn/fail),
  feature spread > 3 layers (warn), reach into bottleneck nodes (note), test
  presence — presence only, not coverage (warn).

## Two non-obvious things that were wrong first

**The sys.path root decides whether the graph exists at all.** wilson's code
imports `api.models`, not `server.api.models`, because `manage.py` puts
`server/` on sys.path. Analysing `server` as the package (it has an
`__init__.py`, so discovery finds it) resolved every intra-project import as
external: 647 modules, **58 imports**. With `root=server/` and its apps as the
packages: 630 modules, **1744 imports**. `discover_packages()` now detects the
Django layout via `manage.py`, `--root` overrides it, and the script warns when
imports < modules/4 so this cannot pass silently again.

**A dependency matrix is only readable under a topological order.** Ordered
alphabetically, which side of the diagonal a cell falls on is meaningless.
`topological_order()` condenses SCCs (Tarjan) and Kahn-sorts the DAG, so every
ordinary import lands above the diagonal and anything below it is a genuine
back-edge. Verified on FMS: 37 imports, all above, 0 cycles.

Layers are always one segment coarser than nodes (`layer_depth_for`), otherwise
the layer matrix duplicates the node graph and the page hides it — which is
exactly the big-repo case where it is most useful.

## Findings from the first runs

- **FMS** (35 modules): acyclic, clean layering. Top hotspot
  `app/ingestion/players.py` (churn 219, cc 7).
- **wilson** (630 modules, 278 package nodes, ~90s): `son.models` has fan-in
  **602** — the god-module. One 10-module cycle across `macolito`/`phys_red`/`son`.
  `api ↔ wilson` imports run both ways (17). Worst hotspots:
  `server/api/forest/match.py` (churn 4963, cc 50, 10 authors),
  `server/api/views/physical_v3_view.py` (cc 90),
  `server/son/models/match_provider_manager.py` (churn 2710, cc 37).
- **hub-mr on wilson** (`HEAD~25..HEAD`, 2m46s): verdict *regression* — 20 changed
  files carry a function with cc ≥ 20, and `son.models`' fan-in climbed 561 → 602
  in 25 commits. No new cycles or layer coupling. That fan-in trend is the
  clearest "slope" signal the tool produces.
- **hub-mr on FMS** (`8c707fd..13590d7`, the player domain landing on the bare
  template): verdict *watch* — 14 new nodes, 26 new imports, 9 brand-new layer
  pairs. A first feature on an empty template trips *spread* and *new layer
  coupling* by construction; read those relative to how much existed before.

## Limits

Python imports only — no call graph, no runtime coupling, no JS/TS. Anything
wired through Django signals, SQS/SNS, or HTTP looks unconnected (relevant for
wilson's lambdas and the football pipeline). At `--level package`, `cc_max` is
the worst member file and `MI` is the mean.
