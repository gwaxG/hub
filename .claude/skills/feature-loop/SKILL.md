---
name: feature-loop
description: Take a SkillCorner ticket from investigation to validated MRs in a loop. tech-explorer + football-explorer judge the ticket, Python Backend Engineer implements, code-reviewer reviews, prerelease-planner prereleases and deploys (dev-workflow), qa-planner plans and qa_run.py runs the tests, qa-verifier judges. Any failure restarts the loop; it ends with the MRs, a feature description and the validation scenarios. Use when the user gives a ticket to implement, or runs /feature-loop <ticket>.
---

# feature-loop

You (the main session) are the **conductor**. Agents do the work; you pass the context between them, enforce the
gates, and keep the state file current. Subagents can't spawn agents or ask the user anything, so every user
question goes through you. The mechanics (pirlo, pinning, envs, QA runner) live in the `dev-workflow` skill.

## State

`~/.cache/skillcorner-dev/<ticket-slug>/`:

- `state.md`: the ticket link, the env, repos/worktrees/branches/MRs, standing approvals, and one line per iteration
  (`iter N: <phase reached> → <outcome>`).
- `tech-brief.md`, `football-brief.md`, `plan.md` (what should be done), `iter-N/` (review notes, `plan.yaml`,
  `qa-results.json`, `report.md`).

Update `state.md` after every phase so that a resumed session can continue from it.

## Phase 1: Investigate and judge (once, and again if a later phase says the understanding was wrong)

1. Read the ticket (Notion / GitLab / Slack / pasted text). Pick a slug, create the state folder.
2. Spawn **`tech-explorer`** with the ticket and precise questions (use parallel instances for wide features). Then spawn
   **`football-explorer`** with the ticket + tech brief. Skip football-explorer for purely technical tickets.
3. Write `plan.md` yourself from both briefs:
   - **Verdict**: clear / needs clarification / not feasible as written.
   - **What should be done**, per repo, in release order (libs → son → wilson → football), each with the place
     of interest (`path:line`) and the pattern to follow.
   - **Scope class** → target envs (dev-workflow §0): `mr_<iid>` for every project. Wilson goes to `dev` only when the ticket needs a football pipeline run.
   - **Acceptance criteria** and the **QA scenarios** (from the football brief).
4. **Gate**: show the verdict, the plan and the env to the user.
   - Stop and ask if the verdict isn't "clear" or there are blocking product questions.
   - Ask once whether QA plans may run without asking again, within a cap (env, at most N matches, mutating
     steps yes/no). Record the answer.

## Phase 2: Implement ⇄ review

1. One worktree + branch per repo (`feat/<brief-subject>` or `fix/…`), never in the workspace mirror.
2. Spawn **`Python Backend Engineer`** per repo, in release order. Give it `plan.md`, both briefs, its worktree,
   and (from iteration 2 on) the failure report it must fix. It implements, adds tests, runs targeted tests
   (never the full wilson suite, never `-n auto`), runs ruff, bumps library versions, commits and pushes.
3. Spawn **`code-reviewer`** with the ticket, `plan.md` and the diff (`git diff origin/main...<branch>`), but
   **not** the engineer's reasoning. Blocking findings go back to the engineer. At most 3 review rounds per
   iteration; after that, stop and show the user the disagreement.
4. Open (or update) a **draft MR** per repo assigned to the user, and link it in `state.md`.

## Phase 3: Prerelease and deploy

Spawn **`prerelease-planner`** with `mode: deploy`, the repos/branches, the env per project, and
`approved_env: dev` only if recorded in `state.md`. If it stops because `dev` is occupied by an unmerged branch,
show the user who holds it and ask for permission. On a yes, record it as a standing approval for this loop and
respawn the agent. Wait for its table. A deployed commit that doesn't match the branch head is a failure (go to
"On failure").

## Phase 4: QA

1. Spawn **`qa-planner`** with the worktrees, MRs, env, `plan.md` and both briefs → `iter-N/plan.yaml`.
2. Approval: run without asking only if the plan stays within the standing QA approval. Otherwise show the step
   table and wait for a yes.
3. Run the plan in the background:
   `uv run ~/.claude/agents/qa/qa_run.py iter-N/plan.yaml --out iter-N/qa-results.json [--approved]`.
4. Spawn **`qa-verifier`** with the folder and MRs. In this loop it posts the MR note **only when the verdict is passed**.

## On failure: restart the loop

Classify the failure using the verifier report (or the review / deploy failure):

| Cause | Restart at |
|---|---|
| bug in the change | Phase 2: the engineer gets the verifier report and the reviewer re-checks the fix |
| wrong understanding of the ticket or the domain | Phase 1, step 2: rerun the explorers with the failure, rewrite `plan.md`, re-gate if the plan changed |
| bad QA plan (wrong oracle or name) | Phase 4, step 1, with the verifier's notes |
| missing files on dev (verifier lists them) | copy them from prod with `s3-copy` (dev-workflow §4; ask first unless covered by the standing approval), then rerun only the affected QA steps with `--only`. No reimplementation or re-review, and it doesn't count as a failed iteration |
| environment (deploy lock, infra outage) | tell the user and wait; this isn't a code failure |

Log the iteration in `state.md` and keep the MR branches; new commits stack on them. **After 3 failed iterations,
stop** and show the user the history and the recurring cause.

## On success: hand-off

Show the user:

1. **MRs**: one clickable link per repo, with branch and status.
2. **What was implemented**: a short feature description, mapped to the acceptance criteria.
3. **How it was validated**: env and deployed commit, the QA scenarios (API checks, lambdas, pipeline matches and
   SFN status, data queried after the green run), and a link to `report.md`.
4. **What's left**: the user marks the MRs ready and merges the libs. Then run `prerelease-planner mode: repin`.

Also fill each MR description (use the `mr-description` skill) with the feature and validation sections. Then
run `prerelease-planner mode: teardown` for custom stacks, and file the briefs' durable discoveries into hub `docs/`.

## Never

Deploy a shared env or run pipelines/mutating QA without a recorded approval, merge MRs, push to `main`, or keep
looping past 3 failed iterations.
