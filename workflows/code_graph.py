# /// script
# requires-python = ">=3.11"
# dependencies = ["grimp>=3.17", "radon>=6.0"]
# ///
"""code_graph.py — import graph + code metrics for a Python repo, as one HTML page.

Analyses a repository (strictly read-only), derives the module import graph with
`grimp`, enriches every node with structural, complexity and git-history
metrics, and renders a self-contained report from
`workflows/templates/code_graph.html`.

This is the whole-repo view: "what does this codebase look like". For "how does
this branch's feature integrate into it", use `workflows/mr_graph.py`. Both
share `codegraph_core.py` and one stylesheet.

Nothing is written inside the analysed repository — grimp's on-disk cache is
disabled and the report goes to `--out` (default `hub/tmp/code-graph/`).

Per-node metrics
  loc        source lines of code (radon `sloc`)
  ca / ce    afferent / efferent coupling — fan-in / fan-out
  i          instability, Ce / (Ca + Ce)            0 = stable, 1 = unstable
  a          abstractness, abstract classes / all classes
  dist       |A + I - 1| — distance from Martin's "main sequence"
  cc_max     worst cyclomatic complexity inside the node
  mi         radon maintainability index (0-100, higher is better)
  commits    commits touching the node in the history window
  churn      lines added + deleted in the window
  authors    distinct authors in the window (bus factor)

Repo-level: dependency cycles (Tarjan SCCs), a layer coupling matrix, and a
per-file churn x complexity hotspot ranking.

Usage:
    uv run workflows/code_graph.py workspace/skillcorner/software/football-metadata-service
    uv run workflows/code_graph.py <repo> --package app --level module
    uv run workflows/code_graph.py <repo> --root server --depth 3
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from codegraph_core import (
    AUTO_PACKAGE_THRESHOLD,
    DEFAULT_EXCLUDES,
    DEFAULT_SINCE,
    OUT_ROOT,
    TEMPLATES,
    Options,
    analyse,
    render,
)

TEMPLATE = TEMPLATES / "code_graph.html"


def print_summary(payload: dict) -> None:
    """Print the headline numbers so the terminal is useful on its own."""
    nodes = payload["nodes"]
    print("\n" + "=" * 60)
    print(f"nodes    : {len(nodes)}")
    print(f"imports  : {payload['meta']['imports']}")
    print(f"cycles   : {len(payload['cycles'])}")
    for component in payload["cycles"][:3]:
        print(f"  - {len(component)} modules: {', '.join(component[:4])} ...")
    print("\nmost depended upon (highest fan-in):")
    for node in sorted(nodes, key=lambda n: n["ca"], reverse=True)[:5]:
        print(f"  {node['ca']:>4} <- {node['id']}  (I={node['i']}, MI={node['mi']})")
    print("\ntop hotspots (churn x complexity):")
    for row in payload["hotspots"][:5]:
        print(
            f"  {row['score']:.3f}  {row['path']}  "
            f"(churn={row['churn']}, cc={row['cc_max']}, authors={row['authors']})"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path, help="repository to analyse (read-only)")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="directory placed on sys.path (default: auto — repo, src/, or a Django project dir)",
    )
    parser.add_argument(
        "--package",
        action="append",
        default=[],
        help="top-level package to analyse (repeatable; auto-detected if omitted)",
    )
    parser.add_argument(
        "--level",
        choices=["auto", "module", "package"],
        default="auto",
        help=f"graph granularity (auto: package above {AUTO_PACKAGE_THRESHOLD} modules)",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="dotted segments kept per node at package level (default 2)",
    )
    parser.add_argument(
        "--since",
        default=DEFAULT_SINCE,
        help=f"git history window (default {DEFAULT_SINCE!r})",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=None,
        help=f"drop modules containing this string (default {DEFAULT_EXCLUDES})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_ROOT,
        help=f"report directory (default {OUT_ROOT})",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    root = args.repo.expanduser().resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 2
    if not TEMPLATE.is_file():
        print(f"ERROR: template missing: {TEMPLATE}", file=sys.stderr)
        return 2

    print(f"Repository : {root}")
    payload = analyse(
        Options(
            tree_root=root,
            git_root=root,
            root=args.root,
            packages=args.package,
            level=args.level,
            depth=args.depth,
            since=args.since,
            excludes=args.exclude
            if args.exclude is not None
            else list(DEFAULT_EXCLUDES),
        )
    )
    meta = payload["meta"]
    report = render(
        payload,
        TEMPLATE,
        args.out.expanduser().resolve(),
        meta["repo"],
        {
            "TITLE": f"{meta['repo']} — code graph",
            "REPO": meta["repo"],
            "GENERATED": meta["generated"],
        },
    )
    print_summary(payload)
    print(f"\nreport   : {report}")
    print(f"data     : {report.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
