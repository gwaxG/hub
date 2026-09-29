---
name: hub-mr
description: Evaluate how a feature branch or MR integrates into the existing codebase — where it sits in the dependency graph, whether it introduced cycles, new layer coupling or unstable dependencies, and whether repo-level metrics got worse. Produces an HTML report with a verdict. Use when the user asks whether a branch/MR/feature integrates well, wants a structural review of a change, or wants before/after architecture metrics.
---

# hub-mr

Runs `workflows/mr_graph.py`, which analyses the repository **twice** — at the
merge base with the target branch and at the branch head — and reports the
difference. Companion to `hub-graph` (whole-repo snapshot); they share
`workflows/codegraph_core.py`, one stylesheet and one set of canvas renderers.

Your job is to launch it and then **read the verdict for the user**, turning
findings into decisions. The analysis itself is deterministic — no LLM.

Both revisions are materialised with `git archive` into `hub/tmp`, so the
analysed repo is never checked out, switched or dirtied. **Committed state
only** — uncommitted work in the tree is not measured.

## The three questions it answers

**Where is it?** Every node is marked `new` / `touched` / `existing` and every
import the change introduced is drawn on top of the existing graph, so the
feature's footprint and its blast radius are visible in place rather than as a
file list. The graph has *feature only* and *feature + neighbours* scopes.

**Is it a slope?** Repo-level aggregates at base vs head — cycles, nodes inside
cycles, median instability, median MI, nodes below MI 65, highest fan-in, worst
complexity, coupled layer pairs, two-way layer pairs. Each is tagged improved /
worsened / no-directional-meaning. Several amber arrows at once is the slope.

**Is it sound?** Eight named checks, `pass` / `note` / `warn` / `fail`:

| Check | Fires when | Why it matters |
|---|---|---|
| New dependency cycles | **fail** | the clearest structural regression; nothing in a loop can be extracted or tested alone |
| New two-way layer pairs | **fail** | two layers importing each other can never be separated |
| New layer coupling | warn | a layer pair talks for the first time — decide deliberately, then encode it as an `import-linter` contract |
| Stable dependencies (SDP) | warn | a new import runs from a *more* stable node to a *less* stable one, so volatile code now ripples into expensive-to-change code |
| Complexity budget | warn / **fail** | a changed file has cc ≥ 11 (warn) or ≥ 20 (fail), or MI < 65 |
| Feature spread | warn | the change touches more than 3 layers — usually one concept missing a home |
| Reach into bottleneck nodes | note | new dependencies on already heavily-imported nodes deepen an existing bottleneck |
| Tests present | warn | production files changed with no test file added or modified — **presence, not coverage** |

The verdict is `clean` / `watch` / `regression`, derived from the checks — not a
composite score, because a made-up number would hide which finding mattered.

## Steps

1. **Run it.** Default compares `HEAD` against `main` (then `master`):

   ```bash
   uv run workflows/mr_graph.py workspace/skillcorner/software/football-metadata-service
   ```

   For a specific range, or when the branch isn't checked out:

   ```bash
   uv run workflows/mr_graph.py <repo> --base <sha> --head <branch-or-sha>
   ```

   To review an MR whose branch is not in the mirror, fetch it into a **worktree**
   (never switch the mirror) and point `--head` at the branch — or pass the two
   SHAs directly, which needs no checkout at all.

2. **Check the header line.** `root` and `packages` must look right; Django
   repos need `--root server` style handling (see `hub-graph` step 2). The script
   forces the base analysis to use the head's level, depth and sys.path root, so
   the two snapshots are always comparable.

3. **Read the report for the user.** Lead with the verdict, then the findings
   that change what they should do:
   - a **fail** is a merge blocker — say which import closes the cycle;
   - **new layer coupling** is the moment to add an `import-linter` contract;
   - an **SDP violation** names a specific edge to invert (depend on an
     abstraction, or move the code);
   - **spread** across many layers usually means a missing module;
   - worsened aggregates matter in aggregate — one amber arrow is noise, five is a trend.

4. **Give the path**, and offer to open it or publish it as an Artifact.

## Options

Shares `--root`, `--package`, `--level`, `--depth`, `--since`, `--exclude`,
`--out` with `hub-graph` (same meanings), plus:

| Flag | Default | Notes |
|---|---|---|
| `--head` | `HEAD` | branch or commit under review |
| `--target` | `main`, then `master` | branch being integrated into; the base is `git merge-base target head` |
| `--base` | — | explicit base commit; skips the merge-base lookup |
| `--fail-on never\|warn\|fail` | `never` | exit non-zero at that verdict level, for CI |
| `--keep-snapshots` | off | leave the extracted trees in `hub/tmp` for inspection |

Artefacts: `hub/tmp/code-graph/<repo>-mr.{html,json}` (gitignored).

## Notes

- **Runtime is two full analyses** — ~10s for a small service, ~3min for wilson.
- **Python imports only.** No call graph, no runtime coupling, no JS/TS. A
  feature wired through Django signals, SQS/SNS or HTTP looks unconnected —
  say so rather than reporting "no integration".
- **A first commit looks bad by design**: an initial feature landing on a bare
  template legitimately trips *spread* and *new layer coupling*, because every
  pair is new. Read those warns relative to how much existed before.
- The **test check is a presence proxy**, not coverage. Don't report it as coverage.
- `--fail-on` makes this usable as a CI gate. Start report-only; cycles and
  two-way layers are the two findings worth blocking on first.
