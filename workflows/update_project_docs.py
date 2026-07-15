# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""update_project_docs.py — consume the reconciliation queue.

Default action builds a deterministic reconciliation *plan*: dedup the queue,
refresh generated indexes, map each edited source path to candidate docs, and
classify its likely impact. The launching skill hands the plan to Agent subagents
that write the curated docs, then calls ``--resolve`` to clear handled paths.

    uv run workflows/update_project_docs.py                 # print the plan
    uv run workflows/update_project_docs.py --resolve p1 p2  # drop resolved paths
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import generate, paths, queue  # noqa: E402

_IMPACT_RULES = [
    ("no_documentation_impact", ("/test", "test_", "_test.", "/tests/")),
    (
        "interface_change",
        ("router", "/api/", "endpoint", "schema", "serializ", "graphql"),
    ),
    ("domain_rule", ("/migrations/", "models", "domain")),
    (
        "workflow_change",
        ("pipeline", "/sfn", "stepfunction", "step_function", "/lambda", "workflow"),
    ),
    ("operations_change", ("pulumi", "terraform", "/infra", "deploy", "helm", "chart")),
    ("documentation_only", (".md", ".rst")),
]


def classify_impact(source_path: str) -> str:
    p = source_path.lower()
    for label, needles in _IMPACT_RULES:
        if any(n in p for n in needles):
            return label
    return "curated_documentation"


def regenerate_indexes(hub_root: Path) -> None:
    generate.build_source_map(hub_root)
    generate.build_graph(hub_root)


def build_plan(hub_root: Path) -> list[dict]:
    memory = paths.memory_dir(hub_root)
    records = queue.dedup(queue.unresolved(queue.read_records(memory)))
    smap = _load_source_map(hub_root)
    plan = []
    for rec in records:
        src = rec.get("source_path", "")
        candidates = rec.get("candidate_docs") or paths.map_source_to_docs(src, smap)
        plan.append(
            {
                "source_path": src,
                "exists": (hub_root / src).exists(),
                "candidate_docs": candidates,
                "impact": classify_impact(src),
            }
        )
    return plan


def _load_source_map(hub_root: Path) -> list[dict]:
    f = paths.generated_dir(hub_root) / "source-map.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("entries", [])
    except (json.JSONDecodeError, OSError):
        return []


def print_plan(plan: list[dict]) -> None:
    if not plan:
        print("reconciliation queue is empty — nothing to update.")
        return
    print(f"# Reconciliation plan ({len(plan)} source path(s))\n")
    for item in plan:
        docs = (
            ", ".join(item["candidate_docs"])
            or "(no mapped doc — decide where it belongs)"
        )
        flag = "" if item["exists"] else " [deleted]"
        print(
            f"- {item['source_path']}{flag}\n    impact: {item['impact']}\n    docs: {docs}"
        )
    print("\n```json")
    print(json.dumps(plan, indent=2))
    print("```")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resolve",
        nargs="+",
        metavar="SOURCE_PATH",
        help="remove these source paths from the queue",
    )
    args = parser.parse_args()

    hub_root = paths.find_hub_root(Path.cwd())
    if args.resolve:
        removed = queue.resolve(paths.memory_dir(hub_root), set(args.resolve))
        print(f"resolved {removed} queue record(s).")
        return 0

    regenerate_indexes(hub_root)
    print_plan(build_plan(hub_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
