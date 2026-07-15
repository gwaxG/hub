---
name: hub-ingest-repository
description: Ingest a workspace repository into the curated docs/ vault — inventory it deterministically, then dispatch agents to extract graph nodes, architecture, domain, workflow and interface knowledge. Use to seed or refresh knowledge about a specific repo under workspace/.
---

# ingest-repository

Thin launcher. `workflows/ingest_repository.py` does the mechanical inventory;
`Agent` subagents do the semantic analysis; you file the results into the vault.

## Steps

1. **Inventory the repo:**
   ```bash
   uv run workflows/ingest_repository.py workspace/<group>/.../<repo>
   ```
   Writes `docs/generated/inventory-<repo>.json` and prints top-level dirs,
   language mix, detected frameworks and whether it has tests.

2. **Analyze meaningful components.** Using the inventory as a map, dispatch
   `Agent` subagents (e.g. `Explore`) to read the repo and extract *durable,
   non-obvious* knowledge — responsibilities, architecture, domain rules,
   interfaces, workflows, operations. **Skip trivial modules**; do not restate code.

3. **File into the vault.** Create/update:
   - a graph node under `docs/graph/repositories/<repo>.md` (responsibility +
     `related` edges to services/packages/databases it depends on);
   - notes in `docs/architecture/`, `docs/domain/`, `docs/workflows/`,
     `docs/interfaces/`, `docs/operations/` where genuinely warranted.
   Record `source_paths`, add `related` links, and set `last_verified` to today
   for what you actually inspected.

4. **Refresh the graph and validate:**
   ```bash
   uv run workflows/refresh_graph.py
   uv run workflows/validate_docs.py
   ```

5. **Report** which nodes/notes were created or updated, and note anything left
   undocumented on purpose.

## Notes

- Prefer updating an existing note over creating a near-duplicate.
- The vault should get more coherent, not merely larger — one fact, one home.
