# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""refresh_graph.py — regenerate docs/generated/graph.json from docs/graph/.

Thin CLI over ``hub_lib.generate.build_graph`` (shared with the MR hook). The
hand-written nodes under docs/graph/ are the source of truth; this derives the
machine index and must not be edited by hand.

    uv run workflows/refresh_graph.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hub_lib import generate, paths  # noqa: E402


def main() -> int:
    hub_root = paths.find_hub_root(Path.cwd())
    nodes, edges, target = generate.build_graph(hub_root)
    print(
        f"graph: {len(nodes)} node(s), {len(edges)} edge(s) -> {target.relative_to(hub_root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
