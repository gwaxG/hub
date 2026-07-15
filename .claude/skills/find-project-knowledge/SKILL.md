---
name: find-project-knowledge
description: Search the curated docs/ vault for existing knowledge before answering or documenting. Deterministic ranked retrieval over front matter + content, optionally refined by an agent. Use to check "what do we already know about X?" across the vault.
---

# find-project-knowledge

Thin launcher over `workflows/find_knowledge.py`. The workflow owns deterministic
retrieval; refine the shortlist yourself or with an `Agent` if the question is
semantic.

## Steps

1. **Search:**
   ```bash
   uv run workflows/find_knowledge.py <terms...> [--type workflow|domain|interface|...] [--limit 10]
   ```
   Prints ranked `[score] path — title` with a matching snippet.

2. **Refine.** Read the top hits. For a nuanced question, dispatch an `Agent` to
   read the shortlisted docs and synthesize an answer with citations to the doc
   paths. Trust current source over the vault when they disagree (see the
   source-of-truth precedence in `CLAUDE.md`).

3. **Report** the answer with the doc paths it came from. If the vault has no
   good hit, say so — that gap is a candidate for `/ingest-repository` or a new note.

## Notes

- Retrieval is keyword-scored (title weighted); it finds candidates, it does not
  rank meaning — that is the agent's job.
- Don't fabricate: if it isn't in the vault or the source, say it isn't.
