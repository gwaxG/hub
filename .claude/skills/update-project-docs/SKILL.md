---
name: update-project-docs
description: Reconcile the documentation queue — consume docs/memory/pending-updates.jsonl, inspect the final git diff, update affected curated docs when behavior is established, then clear resolved entries. Use after doing real work in a workspace repo, or when the queue is non-empty.
---

# update-project-docs

Thin launcher over `workflows/update_project_docs.py`. The workflow owns the
deterministic half (dedup, index refresh, source→doc mapping, impact
classification); **you** own the semantic half (deciding what actually changed and
writing the docs), dispatched to `Agent` subagents.

## Steps

1. **Build the plan** (also refreshes `docs/generated/` indexes):
   ```bash
   uv run workflows/update_project_docs.py
   ```
   Each entry lists a changed `source_path`, its likely `impact`
   (`interface_change`, `domain_rule`, `workflow_change`, `operations_change`,
   `documentation_only`, `no_documentation_impact`, `curated_documentation`), and
   `candidate_docs`.

2. **Inspect the real change.** For each path with documentation impact, look at
   the **final git diff** in the relevant worktree/repo — not intermediate edits.
   Skip anything that netted to no behavior change, is experimental, or reverted.

3. **Update docs — only when behavior is established.** Dispatch an `Agent` per
   affected doc (or cluster) to update the candidate doc, or create one in the
   right taxonomy folder when none exists. Set `source_paths`, add `related`
   links, and set `last_verified` to today **only because you inspected the
   source**. Never document speculative/unfinished work as current behavior. Use
   `/create-adr` when the change reflects a real architectural decision.

4. **Validate:**
   ```bash
   uv run workflows/validate_docs.py
   ```

5. **Resolve** the paths you handled (drops them from the queue):
   ```bash
   uv run workflows/update_project_docs.py --resolve <source_path> [<source_path> ...]
   ```

6. **Report** which docs changed and what remains unresolved (deferred paths stay
   in the queue for next time).

## Notes

- `no_documentation_impact` paths (tests, etc.) can be resolved without doc edits.
- The plan's `impact` is a deterministic hint, not a verdict — the diff decides.
