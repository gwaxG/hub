---
name: feature
description: Take a SkillCorner ticket from investigation to validated MRs in one session, without spawning agents. Investigate the code and the football domain, plan, implement, self-review, prerelease and deploy (dev-workflow), plan and run QA with qa_run.py, judge the results. Any failure restarts the loop; it ends with the MRs, a feature description and the validation scenarios. Use when the user gives a ticket to implement, or runs /feature <ticket>.
---

# feature

You do every phase yourself, in this session, in order. **Never spawn agents** (Agent tool, workflows,
`start_session`). The mechanics (pirlo, pinning, envs, `s3-copy`, QA runner) are in the `dev-workflow` skill;
read only the section the current phase needs.

## Checklists

Each phase names a checklist under `~/.claude/agents/`. Read it **when you reach that phase**, not before, and
follow its procedure, rules and output format. Skip its lines about answering an orchestrator or not being able
to ask the user: you ask the user directly at the gates.

## Token discipline

- Never re-read a file already read in this session. Read line ranges, not whole files.
- `ls` groups, then grep **inside** one repo; `git diff --stat` first, then only the hunks you need.
- Briefs are notes for your future self after a compaction: terse, `path:line` citations, no prose.
- Trim command output (`| tail -n 40`); long runs (deploys, `qa_run.py`) go in the background.
- Don't paste briefs, diffs or plans back to the user; show the gate summaries only.

## Task list

Start every run with exactly these steps as the task list, and advance it as phases complete (on a restart, set
the step you go back to as in progress):

1. Investigate ticket (tech + football)
2. Write plan, get approval
3. Implement + self-review
4. Open draft MRs
5. Prerelease + deploy
6. Plan + run QA
7. Judge QA, hand off

## State

`~/.cache/skillcorner-dev/<ticket-slug>/`:

- `state.md`: ticket link, env, repos/worktrees/branches/MRs, standing approvals, one line per iteration
  (`iter N: <phase reached> → <outcome>`).
- `tech-brief.md`, `football-brief.md`, `plan.md`, `iter-N/` (`review.md`, `plan.yaml`, `rationale.md`,
  `qa-results.json`, `report.md`).

Update `state.md` after every phase. On resume, read it first and continue from the last phase reached.

## Phase 1: Investigate and judge

1. Read the ticket (Notion / GitLab / Slack / pasted). Pick a slug, create the state folder.
2. **Tech exploration** (`tech-explorer.md`): write `tech-brief.md`. For a wide feature, explore one repo area at
   a time.
3. **Football check** (`football-explorer.md`): write `football-brief.md` from the ticket + tech brief. Skip it
   for purely technical tickets (CI, infra).
4. Write `plan.md`:
   - **Verdict**: clear / needs clarification / not feasible as written.
   - **What should be done**, per repo in release order (libs → son → wilson → football), each with the place of
     interest (`path:line`) and the pattern to follow.
   - **Scope class** → target envs (dev-workflow §0): `mr_<iid>` for every project; wilson goes to `dev` only
     when the ticket needs a football pipeline run.
   - **Acceptance criteria** and **QA scenarios** (from the football brief).
5. **Gate**: show the verdict, plan and env.
   - Stop and ask if the verdict isn't "clear" or there are blocking product questions.
   - Ask once whether QA plans may run without asking again, within a cap (env, at most N matches, mutating
     steps yes/no). Record the answer in `state.md`.

## Phase 2: Implement ⇄ review

1. One worktree + branch per repo (`feat/<subject>` / `fix/…`), never in the workspace mirror.
2. **Implement** (`engineering-python-backend-engineer.md`), per repo in release order: failing test first,
   minimal code, ruff, **targeted tests only** (never the full wilson suite, never `-n auto`, `-n 2` at most),
   library version bump + `uv lock`, commit, push. From iteration 2, start from the failure report.
3. **Review** (`code-reviewer.md`) as a separate pass that ignores your implementation reasoning: re-read only
   the ticket, `plan.md` and `git diff origin/main...<branch>`, and look for reasons the change is wrong (plan
   coverage, football-brief edge cases, CLAUDE.md coding rules). Write `iter-N/review.md` with Critical / Warning
   / Suggestion. Fix the criticals and review again. **At most 3 rounds**; then stop and show the user the open
   findings.
4. Open (or update) a **draft MR** per repo assigned to the user; link it in `state.md`.

## Phase 3: Prerelease and deploy

Follow `prerelease-planner.md` `mode: deploy` (dev-workflow §0–3): print the ordered actions, then prerelease the
libs, pin the consumers, check `dev` occupancy, deploy, confirm the env tag equals the branch head. `dev` held by
an unmerged branch and no standing approval → ask the user, record a yes in `state.md` as a standing approval.
A deployed commit that doesn't match the branch head is a failure.

Prereleases never appear in `pyproject.toml` specs, which always name the final version (for example
`skcr-models>=0.39.2,<1`). A prerelease may appear only in `uv.lock`, where it is a temporary resolution until the
final version is released and the lock is repinned.

## Phase 4: QA

1. **Plan** (`qa-planner.md`, plan schema included there): write `iter-N/plan.yaml` + `rationale.md`, one check
   per behaviour change, ≤ 3 matches from recent green runs, names resolved from IaC, never invented.
2. **Approve**: run without asking only within the standing QA approval; otherwise show the step table and wait.
3. **Run** in the background:
   `uv run ~/.claude/agents/qa/qa_run.py iter-N/plan.yaml --out iter-N/qa-results.json [--approved]`.
4. **Judge** (`qa-verifier.md`): per-change verdict with evidence, each failure classified as change / plan /
   environment, `iter-N/report.md`. Post the MR note **only when the verdict is passed**.

## On failure: restart the loop

| Cause | Restart at |
|---|---|
| bug in the change | Phase 2 with the report; review the fix again |
| wrong understanding of the ticket or domain | Phase 1 step 2 with the failure; rewrite `plan.md`, re-gate if it changed |
| bad QA plan (wrong oracle or name) | Phase 4 step 1 with the report's notes |
| missing files on dev | `s3-copy` from prod (dev-workflow §4; ask unless the standing approval covers it), rerun only the affected steps with `--only`. Not a failed iteration |
| environment (deploy lock, infra outage) | tell the user and wait; not a code failure |

Log the iteration in `state.md`; keep the MR branches, new commits stack on them. **After 3 failed iterations,
stop** and show the user the history and the recurring cause.

## On success: hand-off

1. **MRs**: one clickable link per repo, with branch and status.
2. **What was implemented**: short feature description mapped to the acceptance criteria.
3. **How it was validated**: env and deployed commit, QA scenarios (API checks, lambdas, pipeline matches and SFN
   status, data queried after the green run), link to `report.md`.
4. **What's left**: the user marks the MRs ready and merges the libs; then repin (`prerelease-planner.md`
   `mode: repin`).

Also fill each MR description with the `mr-description` skill (feature + validation sections), tear down custom
stacks (`prerelease-planner.md` `mode: teardown`), and file the briefs' durable discoveries into hub `docs/`.

## Never

Spawn agents, deploy a shared env or run pipelines / mutating QA without a recorded approval, merge MRs, push to
`main`, or loop past 3 failed iterations.
