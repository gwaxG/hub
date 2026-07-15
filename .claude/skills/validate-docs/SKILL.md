---
name: validate-docs
description: Validate the curated docs/ vault — YAML front matter, internal links, required metadata, duplicate titles, generated-file markers, stale source paths, and the unresolved reconciliation queue. Use before committing docs or when checking vault health.
---

# validate-docs

Thin launcher. All checks live in `workflows/validate_docs.py`; you just run it
and relay the result.

## Steps

1. **Run the validator:**
   ```bash
   uv run workflows/validate_docs.py
   ```
   It writes `docs/memory/last-validation.json` and `docs/memory/stale-docs.json`,
   prints per-doc errors (`✗`) and staleness warnings (`~`), and exits non-zero
   when there are hard errors.

2. **Report** the counts (errors / stale / unresolved queue) and list the hard
   errors. Errors are blocking; stale entries are advisory (source paths that no
   longer exist, or `status: deprecated`).

3. **If there are errors**, fix them at the source (the offending doc's front
   matter or links) — do not edit `docs/generated/` or `docs/memory/` by hand.
   Re-run to confirm a clean pass.

## Notes

- Validation is read-only apart from the two `docs/memory/` snapshots.
- Staleness is not failure: it flags docs whose `source_paths` vanished, which
  usually means the doc needs re-verification via `/update-project-docs`.
