---
name: refresh-project-graph
description: Regenerate docs/generated/graph.json from the hand-written nodes under docs/graph/ (front matter = node metadata, related = edges). Use after adding or editing graph nodes to rebuild the machine-readable project graph.
---

# refresh-project-graph

Thin launcher over `workflows/refresh_graph.py`. Purely mechanical: the nodes in
`docs/graph/` are the source of truth; this rebuilds the derived index.

## Steps

1. **Regenerate:**
   ```bash
   uv run workflows/refresh_graph.py
   ```
   Reads every node under `docs/graph/` and writes
   `docs/generated/graph.json` (nodes + edges), printing the counts.

2. **Report** the node and edge counts. If a node you expected is missing, its
   file probably lacks front matter or lives outside `docs/graph/`.

## Notes

- Never edit `docs/generated/graph.json` by hand — it is regenerated and
  git-ignored. Add or fix the node Markdown under `docs/graph/` instead.
- Edges come from each node's `related:` list; keep those pointing at real docs.
