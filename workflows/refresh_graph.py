# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""refresh_graph.py — regenerate docs/generated/graph.json from docs/graph/.

Reads every node under docs/graph/ (front matter = node metadata, ``related`` =
outgoing edges) and emits a machine-readable graph index. Hand-written nodes are
the source of truth; this file is derived and must not be edited by hand.

    uv run workflows/refresh_graph.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import frontmatter, paths  # noqa: E402


def collect(hub_root: Path) -> tuple[list[dict], list[dict]]:
    graph_dir = paths.docs_dir(hub_root) / "graph"
    nodes: list[dict] = []
    edges: list[dict] = []
    for doc in sorted(graph_dir.rglob("*.md")):
        if doc.name == "README.md":
            continue
        meta, _ = frontmatter.load(doc)
        node_id = doc.relative_to(paths.docs_dir(hub_root)).as_posix()
        nodes.append(
            {
                "id": node_id,
                "title": meta.get("title", doc.stem),
                "category": doc.parent.name,
                "systems": meta.get("systems") or [],
            }
        )
        for target in meta.get("related") or []:
            edges.append({"from": node_id, "to": target})
    return nodes, edges


def main() -> int:
    hub_root = paths.find_hub_root(Path.cwd())
    nodes, edges = collect(hub_root)
    target = paths.generated_dir(hub_root) / "graph.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "workflows/refresh_graph.py",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": True,
        "nodes": nodes,
        "edges": edges,
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"graph: {len(nodes)} node(s), {len(edges)} edge(s) -> {target.relative_to(hub_root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
