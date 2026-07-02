---
name: changelog
description: Watch what changed across the cloned workspace/ repos since the last run, record it in the root CHANGELOG.md, and keep the docs/ knowledge base current — update a repo's workspace_graph note for notable changes and draft an ADR under docs/adr/ for architectural ("huge") ones. Use when the user wants to track/review recent changes in the workspace, run the changelog, or after /clone-repos pulls new commits.
---

# changelog

Tracks what changed in the repos cloned under `workspace/` (by `/clone-repos`)
since the last run, and keeps the `docs/` knowledge base current. The hub is
Python-only, so the split is:

- **`workflows/changelog.py`** (deterministic) — diffs every workspace repo
  against a persisted per-repo commit-SHA snapshot (`data/changelog_state.json`),
  writes `CHANGELOG.md`, allocates ADR numbers, and advances the state.
- **You (the skill)** dispatch an **Agent per changed repo** to classify the
  change and author the doc update / ADR body. No JavaScript / Workflow scripts.

Because `/clone-repos` does `git pull --ff-only`, the old HEAD is gone by the
time we look — so the watcher keeps its own SHA snapshot and diffs against it.

- **No arg** → whole workspace.
- **A repo or group path** (e.g. `skillcorner/software`) → limit the scan.

## Steps

1. **Plan the run.** `TARGET` is the path the user named, relative to `workspace/`
   (empty = whole workspace).
   ```bash
   uv run workflows/changelog.py plan "skillcorner/software"
   ```
   Prints JSON. Handle the three cases:
   - **`"error"`** → stop and surface it.
   - **`"baseline": true`** → this was the first run; it just recorded the SHA
     snapshot (`seeded` repos). Tell the user "baseline established — re-run after
     the next `/clone-repos` to see changes." Stop.
   - otherwise → `changed` (alias `repos`) is the list of repos with new commits.
     If empty, report "nothing changed since last run" and stop. Also mention
     `newRepos` (cloned since last run — seeded now; suggest `/explain-repo` for
     those) and `unchangedCount`.

2. **Classify + document each changed repo with a subagent.** For every entry in
   `changed`, dispatch a `general-purpose` Agent (run independent repos in
   parallel — multiple Agent calls in one message; batch ~8–10 at a time). Give
   each agent the entry's `repoPath`, `docPath`, `docExists`, `relPath`, `group`,
   `commits`, `diffstat`, and `changedFiles`, with this instruction:

   > Classify and document one repo's recent changes for a reference wiki.
   > **Do not modify the repo** (read-only over `<repoPath>`); you may write only
   > to the doc path below and return an ADR body.
   >
   > You are given the new commits (`<commits>`), the diffstat (`<diffstat>`), and
   > the changed files (`<changedFiles>`) since the last run. Read the existing
   > doc at `<docPath>` (if `docExists`) and, if the diff is ambiguous, inspect
   > the changed files in `<repoPath>` to understand them. Then **classify**:
   >
   > - **architectural** — new service/module, framework or datastore swap, public
   >   API / DB schema / message-contract change, new external integration, IaC
   >   topology change, or auth/security-model change.
   > - **notable** — new feature/endpoint, dependency add or major bump, config
   >   surface change, or a behavior change a reader should know.
   > - **routine** — bugfix, refactor, tests, formatting, docs, chore, minor bump.
   >
   > Actions by category:
   > - `routine` → do nothing to files.
   > - `notable` → **surgically update** the repo's doc at `<docPath>` to reflect
   >   the change (only the affected parts; keep the frontmatter keys and headings
   >   verbatim; match the existing note's structure). If `docExists` is false,
   >   leave the doc to `/explain-repo` and just summarize.
   > - `architectural` → update the doc as above **and** return an ADR: a short
   >   `title` and a `body` with `## Context`, `## Decision`, `## Consequences`.
   >   Do **not** invent an ADR number — the recorder assigns it.
   >
   > Reply with ONLY this JSON (no prose):
   > ```json
   > {"relPath": "<relPath>", "category": "routine|notable|architectural",
   >  "summary": "<one concrete sentence for the changelog>",
   >  "docUpdated": true|false,
   >  "adr": null | {"title": "<short title>", "body": "<markdown body>"}}
   > ```

   (For a single repo you may do this inline yourself instead of spawning an agent.)

3. **Record.** Collect every agent's JSON into a list and write it to a results
   file in the scratchpad, and write the plan JSON alongside it, then:
   ```bash
   uv run workflows/changelog.py record --plan <plan.json> --results <results.json>
   ```
   This appends a dated, newest-first section to `CHANGELOG.md` (one block per
   repo: category, commit count, SHA range, the agent's summary, top commit
   subjects, and links to any doc/ADR), writes each ADR under `docs/adr/` with a
   centrally-assigned `NNNN`, and advances `data/changelog_state.json` to the new
   HEADs. State only moves forward here — so a crashed step 2 re-plans identically.

4. **Report** counts (repos changed, docs updated, ADRs written), list any new
   ADR paths, and offer to open `CHANGELOG.md`.

## Notes

- **State advances only in `record`.** `plan` never mutates state (except seeding
  the baseline on the very first run), so re-planning after a crash is safe.
- **The docs ARE the knowledge base.** Doc updates go into the same
  `docs/workspace_graph/<group>/<repo>.md` notes `/explain-repo` writes; ADRs go
  under `docs/adr/` (see CLAUDE.md "Memory"). Markdown, not HTML.
- **Python only, no JS:** the committed script is `changelog.py`; LLM work is
  Agent dispatch from this skill.
- **Stays inside the hub:** reads `workspace/`, writes only `CHANGELOG.md`,
  `docs/`, and `data/changelog_state.json`. Never outside the repo. Never mutates
  the watched repos.
- **Order of operations:** run `/clone-repos` first (to pull new commits), then
  `/changelog` to record what those pulls brought in.
