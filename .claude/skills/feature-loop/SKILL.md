---
name: feature-loop
description: Take a SkillCorner ticket from investigation to validated MRs in a loop. tech-explorer + football-explorer judge the ticket, the plan is written as one OpenSpec change per repo, Python Backend Engineer implements its tasks, code-reviewer reviews against the specs, prerelease-planner prereleases and deploys (dev-workflow), qa-planner turns spec scenarios into checks and qa_run.py runs them, qa-verifier judges. Any failure restarts the loop; it ends with the MRs, a feature description and the validation scenarios. Use when the user gives a ticket to implement, or runs /feature-loop <ticket>.
---

# feature-loop

You (the main session) are the **conductor**. Agents do the work; you pass the context between them, enforce the
gates, and keep the state file current. Subagents can't spawn agents or ask the user anything, so every user
question goes through you. The mechanics (pirlo, pinning, envs, QA runner) live in the `dev-workflow` skill.

## OpenSpec

The plan is an **OpenSpec change** (the `openspec` CLI, ≥ 2.1), one per touched repo, all with the same kebab-case
change name, living in that repo's feature worktree at `openspec/changes/<change>/`: `proposal.md` (why + verdict),
`specs/` (acceptance criteria as WHEN/THEN scenarios), `design.md` (how, `path:line`), `tasks.md` (checkboxes). It
ships in the repo's MR next to the code and is archived into `openspec/specs/` before the MR is marked ready.

- **Init where missing**: in a worktree with no `openspec/` folder, run `openspec init --tools none --no-animation .`,
  then copy [openspec-config.yaml](openspec-config.yaml) over `openspec/config.yaml`. A repo that already has a
  root keeps its own config. The init is part of the feature's MR.
- **Only you** run the propose / update / archive workflows (the `openspec-propose`, `openspec-update-change`,
  `openspec-archive-change` skills): they ask the user questions. Subagents only read the change and tick tasks.
- Run every `openspec` command from the repo's worktree, so the nearest root is that repo's.

## State

`~/.cache/skillcorner-dev/<ticket-slug>/`:

- `state.md`: the ticket link, the change name, the env, repos/worktrees/branches/MRs, standing approvals, and one
  line per iteration (`iter N: <phase reached> → <outcome>`).
- `tech-brief.md`, `football-brief.md`, `iter-N/` (review notes, `plan.yaml`, `qa-results.json`, `report.md`).
  The plan itself lives in the OpenSpec changes, not here.

Update `state.md` after every phase so that a resumed session can continue from it.

## Phase 1: Investigate and judge (once, and again if a later phase says the understanding was wrong)

1. Read the ticket (Notion / GitLab / Slack / pasted text). Pick a slug (it is also the change name), create the
   state folder.
2. Spawn **`tech-explorer`** with the ticket and precise questions (use parallel instances for wide features). Then spawn
   **`football-explorer`** with the ticket + tech brief. Skip football-explorer for purely technical tickets.
3. Decide the repos, in release order (libs → son → wilson → football). One worktree + branch per repo
   (`feat/<brief-subject>` or `fix/…`), never in the workspace mirror. Init OpenSpec where missing (see above).
4. In each worktree, follow `openspec-propose` with the ticket and both briefs as input, scoped to that repo.
   The config rules make it write the verdict, `path:line` places of interest, scope class → target envs
   (dev-workflow §0: `mr_<iid>` for every project; wilson goes to `dev` only when the ticket needs a football
   pipeline run), testable scenarios and per-repo tasks. Check with `openspec validate <change>`.
5. **Gate**: show the user, per repo, the verdict, the requirements and scenarios, the task groups, and the env.
   - Stop and ask if a verdict isn't "clear" or there are blocking product questions.
   - Ask once whether QA plans may run without asking again, within a cap (env, at most N matches, mutating
     steps yes/no). Record the answer.

## Phase 2: Implement ⇄ review

1. Spawn **`Python Backend Engineer`** per repo, in release order. Give it the change name, its worktree, both
   briefs, and (from iteration 2 on) the failure report it must fix. It reads the change files listed by
   `openspec instructions apply --change <change> --json` (run in its worktree), implements the pending tasks,
   ticks each `- [x]` when done, adds tests, runs targeted tests (never the full wilson suite, never `-n auto`),
   runs ruff, bumps library versions, commits and pushes. If a task needs more than the specs say, it stops and
   reports instead of widening the scope.
2. Spawn **`code-reviewer`** with the ticket, the change (`proposal.md`, `specs/`, `design.md`) and the diff
   (`git diff origin/main...<branch>`), but **not** the engineer's reasoning. Its first check: every scenario is
   covered by code and a test. Blocking findings go back to the engineer. At most 3 review rounds per iteration;
   after that, stop and show the user the disagreement.
3. Open (or update) a **draft MR** per repo assigned to the user, and link it in `state.md`.

## Phase 3: Prerelease and deploy

Spawn **`prerelease-planner`** with `mode: deploy`, the repos/branches, the env per project, and
`approved_env: dev` only if recorded in `state.md`. If it stops because `dev` is occupied by an unmerged branch,
show the user who holds it and ask for permission. On a yes, record it as a standing approval for this loop and
respawn the agent. Wait for its table. A deployed commit that doesn't match the branch head is a failure (go to
"On failure").

Prereleases never appear in `pyproject.toml` specs, which always name the final version (for example
`skcr-models>=0.39.2,<1`). A prerelease may appear only in `uv.lock`, where it is a temporary resolution until the
final version is released and the lock is repinned.

## Phase 4: QA

1. Spawn **`qa-planner`** with the worktrees, MRs, env, the change's `specs/` per repo and both briefs →
   `iter-N/plan.yaml`. One check per scenario (name it `<repo>:<requirement>/<scenario>`), the THEN step as the
   oracle; a scenario that can't be checked on the env is listed as such in `rationale.md`.
2. Approval: run without asking only if the plan stays within the standing QA approval. Otherwise show the step
   table and wait for a yes.
3. Run the plan in the background:
   `uv run ~/.claude/agents/qa/qa_run.py iter-N/plan.yaml --out iter-N/qa-results.json [--approved]`.
4. Spawn **`qa-verifier`** with the folder and MRs; its verdict is per scenario. In this loop it posts the MR note
   **only when the verdict is passed**.

## On failure: restart the loop

Classify the failure using the verifier report (or the review / deploy failure):

| Cause | Restart at |
|---|---|
| bug in the change | Phase 2: the engineer gets the verifier report and the reviewer re-checks the fix |
| wrong understanding of the ticket or the domain | Phase 1, step 2: rerun the explorers with the failure, revise the changes with `openspec-update-change` (reopen ticked tasks whose behaviour changed), re-gate if the specs changed |
| bad QA plan (wrong oracle or name) | Phase 4, step 1, with the verifier's notes |
| missing files on dev (verifier lists them) | copy them from prod with `s3-copy` (dev-workflow §4; ask first unless covered by the standing approval), then rerun only the affected QA steps with `--only`. No reimplementation or re-review, and it doesn't count as a failed iteration |
| environment (deploy lock, infra outage) | tell the user and wait; this isn't a code failure |

Log the iteration in `state.md` and keep the MR branches; new commits stack on them. **After 3 failed iterations,
stop** and show the user the history and the recurring cause.

## On success: hand-off

In each worktree, follow `openspec-archive-change` for the change (it merges the delta specs into
`openspec/specs/` and moves the change to `openspec/changes/archive/`), run `openspec validate --all`, commit and
push. The MR then lands the specs together with the code.

Show the user:

1. **MRs**: one clickable link per repo, with branch and status.
2. **What was implemented**: a short feature description, mapped to the spec requirements.
3. **How it was validated**: env and deployed commit, the QA verdict per scenario (API checks, lambdas, pipeline
   matches and SFN status, data queried after the green run), and a link to `report.md`.
4. **What's left**: the user marks the MRs ready and merges the libs. Then run `prerelease-planner mode: repin`.

Also fill each MR description (use the `mr-description` skill) with the feature and validation sections. Then
run `prerelease-planner mode: teardown` for custom stacks, and file the briefs' durable discoveries into hub `docs/`.

## Never

Deploy a shared env or run pipelines/mutating QA without a recorded approval, merge MRs, push to `main`, or keep
looping past 3 failed iterations.
