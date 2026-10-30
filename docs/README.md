# docs/ — memory file lake

A flat **file lake**: one Markdown file per note, nothing else — no subfolders.
Each note starts with `repo` / `mr` / `verified_at` frontmatter (see `../CLAUDE.md`);
`uv run workflows/lint_docs.py` keeps the lake coherent. Verify against source
before trusting a note.

Index: [`../MEMORY.md`](../MEMORY.md) — one line per file. Update it in the same
change whenever you add, rename, or remove a file here. This README is the only
non-note file; don't list it in the index.
