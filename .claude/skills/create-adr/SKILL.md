---
name: create-adr
description: Create a numbered Architecture Decision Record under docs/architecture/decisions/. Use when a choice has meaningful alternatives or long-term consequences worth recording (context, decision, alternatives, consequences, status).
---

# create-adr

Thin launcher over `workflows/new_adr.py`, which allocates the next NNNN number
and writes a template. You fill in the narrative from the real decision.

## Steps

1. **Stamp the ADR:**
   ```bash
   uv run workflows/new_adr.py "<short decision title>" [--status proposed|current]
   ```
   Prints the created path, e.g. `docs/architecture/decisions/0003-<slug>.md`.

2. **Fill it in.** Edit the new file: **Context** (forces at play, why now),
   **Decision**, **Alternatives considered** (with trade-offs), **Consequences**
   (including migration implications), **Status**. Set `systems`, `source_paths`
   and `related` links; set `last_verified` if you grounded it in current source.

3. **Validate:**
   ```bash
   uv run workflows/validate_docs.py
   ```

4. **Report** the ADR number, title and status.

## Notes

- Write an ADR only when there were real alternatives or lasting consequences —
  not for routine choices.
- Superseding a decision: add a new ADR and set the old one's `status: deprecated`
  with a `related` link forward.
