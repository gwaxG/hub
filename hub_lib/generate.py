"""Deterministic generators for ``docs/generated/`` (stdlib only).

Shared by the workflows (`source_map`, `refresh_graph`) and the MR hook so index
regeneration has a single implementation. No third-party deps — safe to call from
a stdlib-only hook.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from hub_lib import frontmatter, paths


def _banner(generator: str) -> dict:
    return {
        "generated_by": generator,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "complete": True,
    }


def _write(target: Path, payload: dict) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def build_source_map(hub_root: Path) -> tuple[list[dict], Path]:
    """Map each curated doc's ``source_paths`` → docs/generated/source-map.json."""
    entries: list[dict] = []
    for doc in paths.iter_curated_docs(hub_root):
        meta, _ = frontmatter.load(doc)
        sources = meta.get("source_paths") or []
        if not sources:
            continue
        entries.append(
            {
                "doc": doc.relative_to(hub_root).as_posix(),
                "title": meta.get("title", ""),
                "type": meta.get("type", ""),
                "source_paths": sources,
            }
        )
    target = _write(
        paths.generated_dir(hub_root) / "source-map.json",
        {**_banner("workflows/source_map.py"), "entries": entries},
    )
    return entries, target


def build_graph(hub_root: Path) -> tuple[list[dict], list[dict], Path]:
    """Derive docs/generated/graph.json from the nodes under docs/graph/."""
    graph_dir = paths.docs_dir(hub_root) / "graph"
    nodes: list[dict] = []
    edges: list[dict] = []
    for doc in sorted(graph_dir.rglob("*.md")) if graph_dir.exists() else []:
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
    target = _write(
        paths.generated_dir(hub_root) / "graph.json",
        {**_banner("workflows/refresh_graph.py"), "nodes": nodes, "edges": edges},
    )
    return nodes, edges, target
