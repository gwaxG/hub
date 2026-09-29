# /// script
# requires-python = ">=3.11"
# dependencies = ["grimp>=3.17", "radon>=6.0"]
# ///
"""mr_graph.py — how does this branch's feature integrate into the codebase?

Analyses a repository twice — at the merge base with the target branch, and at
the branch head — then reports the *difference*: what the feature added, where
it sits in the existing graph, and whether the architecture got worse.

This is the companion to `workflows/code_graph.py` (whole-repo snapshot). Both
share `codegraph_core.py`, one stylesheet and one set of browser renderers.

It answers three questions:

  Where is it?    Every node is marked new / touched / existing, and new imports
                  are drawn as additions on the existing graph, so the feature's
                  footprint and blast radius are visible in place.
  Is it a slope?  Repo-level metrics before vs after — cycles, instability,
                  maintainability, fan-in concentration, layer coupling.
  Is it sound?    Named checks with pass / note / warn / fail:
                  new cycles, new layer coupling, bidirectional layers,
                  the Stable Dependencies Principle, complexity budget,
                  feature spread, reach into god-modules, test presence.

Both revisions are materialised with `git archive` into `hub/tmp` — the analysed
repository is never checked out, switched or dirtied. Only committed state is
measured; uncommitted work in the tree is not included.

Usage:
    uv run workflows/mr_graph.py <repo>                       # HEAD vs main
    uv run workflows/mr_graph.py <repo> --target develop
    uv run workflows/mr_graph.py <repo> --base 8c707fd --head 13590d7
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from codegraph_core import (
    AUTO_PACKAGE_THRESHOLD,
    DEFAULT_EXCLUDES,
    DEFAULT_SINCE,
    OUT_ROOT,
    TEMPLATES,
    Options,
    analyse,
    git,
    render,
    resolve_packages,
    snapshot,
)

TEMPLATE = TEMPLATES / "mr_graph.html"
SNAPSHOT_ROOT = OUT_ROOT / ".snapshots"
SPREAD_LIMIT = 3  # layers a single feature may touch before it looks smeared
GOD_MODULE_PERCENTILE = 0.9  # fan-in rank above which a node counts as a god-module


# ---------------------------------------------------------------------------
# Revisions and the diff
# ---------------------------------------------------------------------------
def resolve_rev(repo: Path, name: str) -> str | None:
    """Full sha for a revision name, or None when it does not resolve."""
    sha = git(repo, "rev-parse", "--verify", "--quiet", name).strip()
    return sha or None


def resolve_target(repo: Path, target: str | None) -> str:
    """The branch the feature is integrating into."""
    candidates = [target] if target else ["main", "master"]
    for name in candidates:
        for ref in (name, f"origin/{name}"):
            if resolve_rev(repo, ref):
                return ref
    raise SystemExit(
        f"ERROR: cannot resolve target branch {candidates} in {repo} — pass --target or --base"
    )


def changed_python_files(repo: Path, base: str, head: str) -> dict[str, str]:
    """Map repo-relative .py path -> status (A added, M modified, D deleted).

    A rename is recorded as a delete of the old path plus an add of the new one,
    which is what matters for "where did the feature land".
    """
    changed: dict[str, str] = {}
    raw = git(repo, "diff", "--name-status", "-M", f"{base}..{head}")
    for line in raw.splitlines():
        parts = line.split("\t")
        status = parts[0][0]
        if status == "R" and len(parts) == 3:
            for path, mark in ((parts[1], "D"), (parts[2], "A")):
                if path.endswith(".py"):
                    changed[path] = mark
            continue
        if len(parts) < 2:
            continue
        if parts[1].endswith(".py"):
            changed[parts[1]] = status
    return changed


def is_test_path(path: str) -> bool:
    """Whether a path looks like a test — used only as a presence proxy."""
    name = Path(path).name
    return (
        name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{path}"
    )


# ---------------------------------------------------------------------------
# Annotating the head graph with the feature's footprint
# ---------------------------------------------------------------------------
def annotate_nodes(head: dict, base: dict, changed: dict[str, str]) -> None:
    """Mark every head node new / touched / existing and attach metric deltas."""
    base_by_id = {n["id"]: n for n in base["nodes"]}
    touched_paths = {p for p, s in changed.items() if s != "D"}
    for node in head["nodes"]:
        was = base_by_id.get(node["id"])
        hits = [p for p in node["paths"] if p in touched_paths]
        node["status"] = "new" if was is None else ("touched" if hits else "existing")
        node["changed_paths"] = hits
        for key in ("loc", "ca", "ce", "cc_max", "mi", "i"):
            node[f"d_{key}"] = round(node[key] - (was[key] if was else 0), 3)


def annotate_edges(head: dict, base: dict) -> set[tuple[str, str]]:
    """Flag head edges absent at base; returns the set of new (importer, imported)."""
    base_ids = [n["id"] for n in base["nodes"]]
    base_pairs = {(base_ids[e["s"]], base_ids[e["t"]]) for e in base["edges"]}
    head_ids = [n["id"] for n in head["nodes"]]
    fresh: set[tuple[str, str]] = set()
    for edge in head["edges"]:
        pair = (head_ids[edge["s"]], head_ids[edge["t"]])
        edge["new"] = pair not in base_pairs
        if edge["new"]:
            fresh.add(pair)
    return fresh


# ---------------------------------------------------------------------------
# Repo-level before/after
# ---------------------------------------------------------------------------
def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2


def layer_pairs(payload: dict) -> set[tuple[str, str]]:
    """Layer pairs with at least one import, self-pairs excluded."""
    layers, matrix = payload["layers"], payload["matrix"]
    return {
        (layers[i], layers[j])
        for i, row in enumerate(matrix)
        for j, count in enumerate(row)
        if count and i != j
    }


def bidirectional_pairs(payload: dict) -> set[frozenset[str]]:
    """Layer pairs importing each other in both directions."""
    pairs = layer_pairs(payload)
    return {frozenset(p) for p in pairs if (p[1], p[0]) in pairs}


def summarise(payload: dict) -> dict:
    """The repo-level aggregates that make a trend visible."""
    nodes = payload["nodes"]
    return {
        "nodes": len(nodes),
        "imports": len(payload["edges"]),
        "loc": sum(n["loc"] for n in nodes),
        "cycles": len(payload["cycles"]),
        "nodes_in_cycles": sum(len(c) for c in payload["cycles"]),
        "median_i": round(median([n["i"] for n in nodes]), 3),
        "median_mi": round(median([n["mi"] for n in nodes]), 1),
        "mi_below_65": sum(1 for n in nodes if n["mi"] < 65),
        "max_fan_in": max((n["ca"] for n in nodes), default=0),
        "max_cc": max((n["cc_max"] for n in nodes), default=0),
        "layer_pairs": len(layer_pairs(payload)),
        "bidirectional_layers": len(bidirectional_pairs(payload)),
    }


# (key, label, "up"|"down"|None — the direction that is an improvement)
TOTAL_SPECS = [
    ("nodes", "nodes", None),
    ("imports", "imports", None),
    ("loc", "lines of code", None),
    ("cycles", "dependency cycles", "down"),
    ("nodes_in_cycles", "nodes inside a cycle", "down"),
    ("median_i", "median instability", None),
    ("median_mi", "median maintainability", "up"),
    ("mi_below_65", "nodes with MI < 65", "down"),
    ("max_fan_in", "highest fan-in", "down"),
    ("max_cc", "worst cyclomatic complexity", "down"),
    ("layer_pairs", "coupled layer pairs", "down"),
    ("bidirectional_layers", "two-way layer pairs", "down"),
]


def build_totals(base: dict, head: dict) -> list[dict]:
    """Before/after rows, each tagged better / worse / neutral."""
    before, after = summarise(base), summarise(head)
    rows = []
    for key, label, better in TOTAL_SPECS:
        delta = round(after[key] - before[key], 3)
        verdict = "neutral"
        if delta and better:
            improved = delta < 0 if better == "down" else delta > 0
            verdict = "better" if improved else "worse"
        rows.append(
            {
                "key": key,
                "label": label,
                "base": before[key],
                "head": after[key],
                "delta": delta,
                "verdict": verdict,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Integration checks
# ---------------------------------------------------------------------------
def check(
    name: str, title: str, status: str, detail: str, items: list | None = None
) -> dict:
    return {
        "id": name,
        "title": title,
        "status": status,
        "detail": detail,
        "items": items or [],
    }


def check_cycles(base: dict, head: dict) -> dict:
    """A feature that closes a dependency loop is the clearest architectural regression."""
    before = {frozenset(c) for c in base["cycles"]}
    added = [c for c in head["cycles"] if frozenset(c) not in before]
    if not added:
        return check(
            "cycles",
            "No new dependency cycles",
            "pass",
            "The graph gained no new loops.",
        )
    return check(
        "cycles",
        "New dependency cycles",
        "fail",
        f"{len(added)} cycle(s) appeared that did not exist at base.",
        [" · ".join(c) for c in added],
    )


def check_layer_coupling(base: dict, head: dict) -> dict:
    """New coupling between layers is where an `import-linter` contract would fire."""
    added = sorted(layer_pairs(head) - layer_pairs(base))
    if not added:
        return check(
            "layer-coupling",
            "No new layer coupling",
            "pass",
            "The feature stayed inside the layer pairs that already talked to each other.",
        )
    return check(
        "layer-coupling",
        "New layer coupling",
        "warn",
        f"{len(added)} layer pair(s) import each other for the first time. "
        "Decide deliberately whether each is allowed, then encode it as a contract.",
        [f"{a} → {b}" for a, b in added],
    )


def check_bidirectional(base: dict, head: dict) -> dict:
    """Two layers importing each other cannot be separated, deployed or tested apart."""
    added = sorted(
        (sorted(p) for p in bidirectional_pairs(head) - bidirectional_pairs(base)),
    )
    if not added:
        return check(
            "two-way-layers",
            "No new two-way layer pairs",
            "pass",
            "No pair of layers started importing each other.",
        )
    return check(
        "two-way-layers",
        "New two-way layer pairs",
        "fail",
        "These layers now import each other, so neither can be extracted or tested alone.",
        [" ↔ ".join(p) for p in added],
    )


def check_stable_dependencies(head: dict, fresh: set[tuple[str, str]]) -> dict:
    """Stable Dependencies Principle: depend in the direction of stability.

    The importer should be the more volatile side (higher instability I). A new
    edge where the importer is *more stable* than what it imports means a
    hard-to-change node now rests on something easy to change.
    """
    by_id = {n["id"]: n for n in head["nodes"]}
    violations = [
        {
            "importer": src,
            "imported": dst,
            "i_importer": by_id[src]["i"],
            "i_imported": by_id[dst]["i"],
            "ca_importer": by_id[src]["ca"],
        }
        for src, dst in sorted(fresh)
        if src in by_id and dst in by_id and by_id[src]["i"] < by_id[dst]["i"]
    ]
    if not violations:
        return check(
            "stable-dependencies",
            "Stable dependencies respected",
            "pass",
            "Every new import runs from the more volatile side to the more stable one.",
        )
    return check(
        "stable-dependencies",
        "Depends toward instability",
        "warn",
        f"{len(violations)} new import(s) run from a more stable node to a less stable one — "
        "changes downstream will now ripple into code that is expensive to change.",
        [
            f"{v['importer']} (I={v['i_importer']}, fan-in {v['ca_importer']}) "
            f"→ {v['imported']} (I={v['i_imported']})"
            for v in violations
        ],
    )


def check_complexity(changed_metrics: list[dict]) -> dict:
    """Complexity budget on the files the feature actually touched."""
    severe = [f for f in changed_metrics if f["cc_max"] >= 20]
    poor = [f for f in changed_metrics if f["cc_max"] >= 11 or f["mi"] < 65]
    if severe:
        return check(
            "complexity",
            "Complexity budget exceeded",
            "fail",
            f"{len(severe)} changed file(s) contain a function with cyclomatic complexity ≥ 20.",
            [f"{f['path']} — cc {f['cc_max']}, MI {f['mi']}" for f in severe],
        )
    if poor:
        return check(
            "complexity",
            "Complexity worth a look",
            "warn",
            f"{len(poor)} changed file(s) have cc ≥ 11 or MI < 65.",
            [f"{f['path']} — cc {f['cc_max']}, MI {f['mi']}" for f in poor],
        )
    return check(
        "complexity",
        "Complexity budget respected",
        "pass",
        "No changed file carries a complex function or a poor maintainability index.",
    )


def check_spread(head: dict) -> dict:
    """A feature smeared across many layers usually means a missing seam."""
    touched = sorted(
        {n["layer"] for n in head["nodes"] if n["status"] in ("new", "touched")}
    )
    if not touched:
        return check(
            "spread",
            "No Python nodes touched",
            "note",
            "The diff changed no analysed module.",
        )
    if len(touched) <= SPREAD_LIMIT:
        return check(
            "spread",
            "Feature is well localised",
            "pass",
            f"It lives in {len(touched)} layer(s): {', '.join(touched)}.",
        )
    return check(
        "spread",
        "Feature is spread thin",
        "warn",
        f"It touches {len(touched)} layers, above the {SPREAD_LIMIT} this check allows. "
        "That usually means one concept is missing a home of its own.",
        touched,
    )


def check_god_module_reach(base: dict, head: dict, fresh: set[tuple[str, str]]) -> dict:
    """New dependents on already heavily-depended-upon nodes deepen a bottleneck."""
    ranked = sorted(base["nodes"], key=lambda n: n["ca"])
    if not ranked:
        return check(
            "god-modules",
            "No baseline to compare",
            "note",
            "Base revision had no nodes.",
        )
    cutoff = ranked[min(len(ranked) - 1, int(len(ranked) * GOD_MODULE_PERCENTILE))][
        "ca"
    ]
    by_id = {n["id"]: n for n in base["nodes"]}
    reached = sorted(
        {dst for _, dst in fresh if dst in by_id and by_id[dst]["ca"] >= max(cutoff, 3)}
    )
    if not reached:
        return check(
            "god-modules",
            "No new load on bottleneck nodes",
            "pass",
            "The feature added no dependency on an already heavily-imported node.",
        )
    return check(
        "god-modules",
        "Reaches into bottleneck nodes",
        "note",
        "The feature adds dependencies on nodes that were already heavily imported "
        f"(fan-in ≥ {max(cutoff, 3)} at base). Not wrong — but each one makes that node harder to change.",
        [f"{node} \u2014 fan-in {by_id[node]['ca']} at base" for node in reached],
    )


def check_tests(changed: dict[str, str]) -> dict:
    """Presence proxy only — that tests exist for this change, not that they cover it."""
    production = [p for p, s in changed.items() if s != "D" and not is_test_path(p)]
    tests = [p for p, s in changed.items() if s != "D" and is_test_path(p)]
    if not production:
        return check("tests", "No production code changed", "pass", "Nothing to cover.")
    if tests:
        return check(
            "tests",
            "Tests accompany the change",
            "pass",
            f"{len(tests)} test file(s) alongside {len(production)} production file(s).",
        )
    return check(
        "tests",
        "No tests in this change",
        "warn",
        f"{len(production)} production file(s) changed and no test file was added or modified. "
        "This checks presence, not coverage.",
        production[:20],
    )


def build_checks(
    base: dict,
    head: dict,
    fresh: set[tuple[str, str]],
    changed: dict[str, str],
    changed_metrics: list[dict],
) -> list[dict]:
    return [
        check_cycles(base, head),
        check_bidirectional(base, head),
        check_layer_coupling(base, head),
        check_stable_dependencies(head, fresh),
        check_complexity(changed_metrics),
        check_spread(head),
        check_god_module_reach(base, head, fresh),
        check_tests(changed),
    ]


def verdict_for(checks: list[dict], totals: list[dict]) -> dict:
    """One headline: is this a clean integration, worth a look, or a regression?"""
    worse = [t["label"] for t in totals if t["verdict"] == "worse"]
    failed = [c["title"] for c in checks if c["status"] == "fail"]
    warned = [c["title"] for c in checks if c["status"] == "warn"]
    if failed:
        return {
            "level": "regression",
            "headline": "Integrates badly",
            "detail": "Blocking findings: " + "; ".join(failed) + ".",
            "worse": worse,
        }
    if warned:
        return {
            "level": "watch",
            "headline": "Integrates, with caveats",
            "detail": "Nothing blocking, but review: " + "; ".join(warned) + ".",
            "worse": worse,
        }
    return {
        "level": "clean",
        "headline": "Integrates cleanly",
        "detail": "Every structural check passed"
        + (
            f", though {len(worse)} aggregate metric(s) moved the wrong way."
            if worse
            else "."
        ),
        "worse": worse,
    }


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def changed_file_metrics(head: dict, changed: dict[str, str]) -> list[dict]:
    """Per-file metrics for the files the feature touched, worst score first.

    Files are read back out of the head hotspot ranking where present; anything
    the ranking dropped (zero churn or zero complexity) still appears, so the
    table covers the whole diff rather than only its dramatic parts.
    """
    hotspots = {h["path"]: h for h in head["hotspots"]}
    by_path = {path: node for node in head["nodes"] for path in node["paths"]}
    rows = []
    for path, status in sorted(changed.items()):
        if status == "D":
            continue
        hot = hotspots.get(path)
        node = by_path.get(path)
        rows.append(
            {
                "path": path,
                "status": status,
                "node": node["id"] if node else "—",
                "cc_max": hot["cc_max"] if hot else (node["cc_max"] if node else 0),
                "mi": hot["mi"] if hot else (node["mi"] if node else 100.0),
                "loc": hot["loc"] if hot else 0,
                "churn": hot["churn"] if hot else 0,
                "authors": hot["authors"] if hot else 0,
                "score": hot["score"] if hot else 0.0,
                "test": is_test_path(path),
            }
        )
    return sorted(rows, key=lambda r: r["score"], reverse=True)


def slim(payload: dict) -> dict:
    """The parts of the base payload the report still needs after the deltas."""
    return {
        "meta": payload["meta"],
        "layers": payload["layers"],
        "matrix": payload["matrix"],
        "cycles": payload["cycles"],
        "node_ids": [n["id"] for n in payload["nodes"]],
    }


def build_payload(
    repo: Path, base_rev: str, head_rev: str, args: argparse.Namespace
) -> dict:
    """Analyse both revisions and assemble the integration report payload."""
    excludes = args.exclude if args.exclude is not None else list(DEFAULT_EXCLUDES)
    changed = changed_python_files(repo, base_rev, head_rev)
    print(f"  changed    : {len(changed)} python file(s) between base and head")

    head_tree = snapshot(repo, head_rev, SNAPSHOT_ROOT / f"{repo.name}-head")
    head_opts = Options(
        tree_root=head_tree,
        git_root=repo,
        rev=head_rev,
        root=args.root,
        packages=args.package,
        level=args.level,
        depth=args.depth,
        since=args.since,
        excludes=excludes,
        label="head",
    )
    head = analyse(head_opts)

    # Base must be analysed at the same granularity and from the same sys.path
    # root, or the deltas compare two different pictures.
    head_base_dir, _ = resolve_packages(head_opts)
    root_rel = head_base_dir.relative_to(head_tree)
    base_tree = snapshot(repo, base_rev, SNAPSHOT_ROOT / f"{repo.name}-base")
    base = analyse(
        Options(
            tree_root=base_tree,
            git_root=repo,
            rev=base_rev,
            root=Path(root_rel)
            if str(root_rel) != "." and (base_tree / root_rel).is_dir()
            else None,
            packages=args.package,
            level=head["meta"]["level"],
            depth=args.depth,
            since=args.since,
            excludes=excludes,
            label="base",
        )
    )

    annotate_nodes(head, base, changed)
    fresh = annotate_edges(head, base)
    base_ids = {n["id"] for n in base["nodes"]}
    head_ids = {n["id"] for n in head["nodes"]}
    changed_metrics = changed_file_metrics(head, changed)
    totals = build_totals(base, head)
    checks = build_checks(base, head, fresh, changed, changed_metrics)

    layer_counts = Counter(
        n["layer"] for n in head["nodes"] if n["status"] in ("new", "touched")
    )
    inside = sum(
        1
        for src, dst in fresh
        if layer_counts.get(_layer_of_id(head, src))
        and layer_counts.get(_layer_of_id(head, dst))
    )

    payload = dict(head)
    payload["meta"] = {
        **head["meta"],
        "base_rev": base_rev,
        "base_commit": base["meta"]["commit"],
        "head_rev": head_rev,
        "head_commit": head["meta"]["commit"],
        "head_branch": head["meta"]["branch"],
        "target": args.target or "auto",
        "changed_files": len(changed),
    }
    payload["base"] = slim(base)
    payload["totals"] = totals
    payload["checks"] = checks
    payload["verdict"] = verdict_for(checks, totals)
    payload["changed"] = changed_metrics
    payload["delta"] = {
        "nodes_added": sorted(head_ids - base_ids),
        "nodes_removed": sorted(base_ids - head_ids),
        "nodes_touched": sorted(
            n["id"] for n in head["nodes"] if n["status"] == "touched"
        ),
        "edges_added": [{"from": s, "into": t} for s, t in sorted(fresh)],
        "layers_touched": sorted(layer_counts),
        "edges_inside_feature": inside,
        "edges_leaving_feature": len(fresh) - inside,
        "unmapped_changes": sorted(
            path
            for path in changed
            if changed[path] != "D"
            and not any(path in n["paths"] for n in head["nodes"])
        ),
    }
    return payload


def _layer_of_id(payload: dict, node_id: str) -> str | None:
    for node in payload["nodes"]:
        if node["id"] == node_id:
            return node["layer"]
    return None


def print_summary(payload: dict) -> None:
    """Terminal report — the same verdict and findings as the page."""
    verdict = payload["verdict"]
    delta = payload["delta"]
    print("\n" + "=" * 68)
    print(f"VERDICT  : {verdict['headline'].upper()}  ({verdict['level']})")
    print(f"           {verdict['detail']}")
    print(
        f"\nfootprint: {len(delta['nodes_added'])} new node(s), "
        f"{len(delta['nodes_touched'])} touched, "
        f"{len(delta['edges_added'])} new import(s) "
        f"across layer(s) {', '.join(delta['layers_touched']) or '—'}"
    )
    print("\nchecks:")
    mark = {"pass": "+", "note": "i", "warn": "!", "fail": "x"}
    for item in payload["checks"]:
        print(f"  [{mark[item['status']]}] {item['title']} — {item['detail']}")
        for line in item["items"][:4]:
            print(f"        - {line}")
    moved = [t for t in payload["totals"] if t["delta"]]
    if moved:
        print("\nmetrics that moved:")
        for row in moved:
            arrow = {"better": "v", "worse": "^", "neutral": "="}[row["verdict"]]
            sign = "+" if row["delta"] > 0 else ""
            print(
                f"  [{arrow}] {row['label']:<30} {row['base']} -> {row['head']}"
                f"  ({sign}{row['delta']})"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, help="repository to analyse (read-only)")
    parser.add_argument(
        "--head", default="HEAD", help="branch or commit under review (default HEAD)"
    )
    parser.add_argument(
        "--target",
        default=None,
        help="branch being integrated into (default: main, then master)",
    )
    parser.add_argument(
        "--base",
        default=None,
        help="explicit base commit; skips the merge-base lookup against --target",
    )
    parser.add_argument(
        "--root", type=Path, default=None, help="directory placed on sys.path"
    )
    parser.add_argument(
        "--package", action="append", default=[], help="package to analyse (repeatable)"
    )
    parser.add_argument(
        "--level",
        choices=["auto", "module", "package"],
        default="auto",
        help=f"graph granularity (auto: package above {AUTO_PACKAGE_THRESHOLD} modules)",
    )
    parser.add_argument(
        "--depth", type=int, default=2, help="segments per node at package level"
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help=f"history window (default {DEFAULT_SINCE!r})",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help=f"drop modules containing this (default {DEFAULT_EXCLUDES})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_ROOT,
        help=f"report directory (default {OUT_ROOT})",
    )
    parser.add_argument(
        "--keep-snapshots",
        action="store_true",
        help="leave the extracted trees in hub/tmp for inspection",
    )
    parser.add_argument(
        "--fail-on",
        choices=["never", "warn", "fail"],
        default="never",
        help="exit non-zero when the verdict reaches this level (for CI)",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    repo = args.repo.expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"ERROR: {repo} is not a git repository", file=sys.stderr)
        return 2
    if not TEMPLATE.is_file():
        print(f"ERROR: template missing: {TEMPLATE}", file=sys.stderr)
        return 2

    head_rev = resolve_rev(repo, args.head)
    if not head_rev:
        print(f"ERROR: cannot resolve --head {args.head!r} in {repo}", file=sys.stderr)
        return 2
    if args.base:
        base_rev = resolve_rev(repo, args.base)
        if not base_rev:
            print(f"ERROR: cannot resolve --base {args.base!r}", file=sys.stderr)
            return 2
    else:
        target = resolve_target(repo, args.target)
        base_rev = git(repo, "merge-base", target, head_rev).strip()
        if not base_rev:
            print(
                f"ERROR: no merge base between {target} and {args.head}",
                file=sys.stderr,
            )
            return 2
        print(f"Target     : {target}")
    if base_rev == head_rev:
        print(
            "ERROR: base and head are the same commit — there is no feature to evaluate.",
            file=sys.stderr,
        )
        return 2

    print(f"Repository : {repo}")
    print(f"Base       : {base_rev[:12]}")
    print(f"Head       : {head_rev[:12]} ({args.head})")

    try:
        payload = build_payload(repo, base_rev, head_rev, args)
    finally:
        if not args.keep_snapshots:
            import shutil

            shutil.rmtree(SNAPSHOT_ROOT, ignore_errors=True)

    meta = payload["meta"]
    name = f"{meta['repo']}-mr"
    report = render(
        payload,
        TEMPLATE,
        args.out.expanduser().resolve(),
        name,
        {
            "TITLE": f"{meta['repo']} — feature integration",
            "REPO": meta["repo"],
            "GENERATED": meta["generated"],
        },
    )
    print_summary(payload)
    print(f"\nreport   : {report}")
    print(f"data     : {report.with_suffix('.json')}")

    level = payload["verdict"]["level"]
    if args.fail_on == "fail" and level == "regression":
        return 1
    if args.fail_on == "warn" and level in ("regression", "watch"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
