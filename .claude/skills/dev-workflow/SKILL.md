---
name: dev-workflow
description: Use on EVERY SkillCorner feature development (wilson, football, shared libs such as data-provider-clients, skcr-utils, skcr-models, son). End-to-end loop — develop, prerelease libs with pirlo, pin them in consumers, deploy to a custom stack or dev/staging with pirlo, validate (API calls, lambda invokes, francli football pipeline green), destroy the stack, repin final versions after merge.
---

# SkillCorner dev workflow

The loop is always: **code → prerelease libs → pin in consumers → deploy → validate → tear down → repin after merge.**
The scenario decides where you deploy.

**Who does what.** The main session orchestrates; the agents below do the work. Sections 1–3, 5 and 6 are carried out by the
`prerelease-planner` agent (it preloads this skill). Spawn it with `mode: deploy | teardown | repin`, repos and
branches, the env, and `approved_env` once the user has said yes to a shared env. Section 4 is done by `qa-planner` →
`qa_run.py` → `qa-verifier`.

To take a whole ticket through every phase in a loop, use the **`feature-loop`** skill. It conducts the agents and
relies on this skill for the mechanics.

## Phase 0: Explore before planning

1. **`tech-explorer`**: spawn it with the ticket/feature and the precise questions you need answered. Run one per
   repo area in parallel if the feature is wide. It writes `~/.cache/skillcorner-dev/<slug>/tech-brief.md`
   (repos, places of interest, contracts, runtime names, open questions).
2. **`football-explorer`**: spawn it with the ticket plus the tech brief. Skip it for purely technical changes
   such as CI or infra. It writes `football-brief.md`: domain rules, edge cases, gaps against the code,
   provider coverage, QA scenarios.
3. Bring the risks and questions to the user, then plan (plan mode or the `Plan` agent; add `Design Adversary`
   for big changes). File the briefs' durable discoveries into hub `docs/`.
4. Pass the briefs on: `qa-planner` gets both (runtime names, QA scenarios). `prerelease-planner` gets the
   release chain.

## 0. Classify the change

**Default: every project deploys to its own custom stack `mr_<iid>`** (the MR iid of that project's MR), wilson
included. A custom wilson stack has its own DB; custom football stacks read the **dev DB**.

| Touched | Deploy target | Validation |
|---|---|---|
| libs + **wilson**, no pipeline needed | wilson → `mr_<iid>` | API requests, lambda invokes |
| libs + **football** | football → `mr_<iid>` | `francli football run --env mr_<iid>` |
| **wilson changes + the ticket needs a football pipeline run** | wilson → **`dev`** (so the pipeline sees the wilson data in the dev DB), football → `mr_<iid>` | change data via wilson on dev (API/lambdas), then run the pipeline on football's `mr_<iid>` |

Wilson goes to `dev` **only** in the last case. Big football changes always end with a pipeline run. Note that
francli's `--env` is a fixed list, so a new `mr_<iid>` may need to be added to francli config before a pipeline can run there.

## 1. Libs: develop and prerelease

Work in a worktree per repo (never in the pristine workspace mirror). For each changed lib:

1. Bump the version in `pyproject.toml` (patch = fix, minor = feature), `uv lock`, `ruff format`/`ruff check --fix`,
   targeted tests.
2. Commit and push the feature branch.
3. From the lib checkout: `uvx pirlo release` (branch/project are read from git; `--version` defaults to
   `prerelease`). The result is a version like `X.Y.Za0+<user>`; read the exact one from the release pipeline.

**son** lives in wilson `server/` (package `son`, `server/pyproject.toml`). A son change needs its own bump
(patch/minor in `server/pyproject.toml`, `env -u VIRTUAL_ENV uv lock` in `server/`) and a prerelease from the wilson branch before wilson lambdas or football
can use it.

## 2. Pin in consumers

On the wilson / football feature branch:

- Set the spec to accept the prerelease (e.g. `son>=0.93.0a0,<1`), `uv lock` in the right dir (wilson root,
  `server/`, each touched lambda; football root/lambdas), commit both `pyproject.toml` and `uv.lock`, push.
- Pinning a prerelease on the consumer branch is fine at review time; the final repin comes after the lib merges
  (step 6).
- uv index gotchas: data-provider-clients uses the named `internal` index — never set `UV_DEFAULT_INDEX` there.
  For wilson pushes (pre-push hook runs `uv lock`) `UV_DEFAULT_INDEX` may be needed.

## 3. Deploy

Run from the consumer checkout on the feature branch. Always `--dry-run` first to confirm project + ref.

```bash
uvx pirlo deploy --env other --stack-name mr_1234 --dry-run  # custom stack (default)
uvx pirlo deploy --env other --stack-name mr_1234
uvx pirlo deploy --env dev                                   # shared env, wilson only when a pipeline needs it
uvx pirlo status --project-name <project>                    # who is deployed where
```

- **Custom stacks**: deploy without asking.
- **`dev`**: shared by the team, so always check occupancy first with `uvx pirlo status --project-name <project>`.
  - **Occupied** (the usual case) by a branch that isn't merged into `main` → **ask the user for permission**
    before deploying. Check "merged" with `git merge-base --is-ancestor origin/<branch> origin/main` or the
    branch's MR state.
  - **Empty**, or holding `main` / an already-merged branch → deploy without asking.
- **`staging`** / **`prod`**: only when the user asks.
- Never use `--force` (it overrides a lock held by someone else's pipeline) unless the user says so.
- Wilson needs `AWS_PROFILE=Production.Skcr-Software-Common-Role`. Wilson ECS tasks with
  `environments: [prod, dev]` are not created on custom stacks — temporarily add the stack name if needed.
- Wait until the deploy is really live: for wilson ECS, PRIMARY deployment `rolloutState=COMPLETED` and a single
  deployment — not just the task-definition pointer.

## 4. Validate

Use the QA agents — plan, approve, run, judge:

1. **Plan**: spawn the `qa-planner` agent with the repo worktrees, branches, MR links, env and scope. It writes
   `~/.cache/skillcorner-qa/<name>/plan.yaml` + `rationale.md` (matches picked from recent green dev runs).
2. **Approve**: show the user the step table. Pipeline runs, `mutates: true` steps and shared envs need an explicit
   yes; then pass `--approved`.
3. **Run** (in the background — pipelines take long):
   `QA_API_USER=… QA_API_PASSWORD=… AWS_PROFILE=… uv run ~/.claude/agents/qa/qa_run.py <dir>/plan.yaml --out <dir>/qa-results.json [--approved]`.
   It refuses to start when the pirlo env tag ≠ branch head (stale deploy). Exit 0 = all passed, 1 = failures,
   2 = refused. Rerun a subset with `--only id1,id2`.
4. **Judge**: spawn the `qa-verifier` agent with the folder and MR URLs. It writes `report.md` and posts the short
   "how it was evaluated" note on each MR.

What the checks look like underneath (also for ad-hoc checks without a plan):

- **wilson**: HTTP requests against the stack's API (client test user creds from the user's CLAUDE.md), lambda
  invokes (`aws lambda invoke` on the stack's function names), DB checks through the API/son. Logs:
  CloudWatch group `wilson-<stack>`.
- **football**: `francli football run --env <env> --match-id <id>` (narrow with `--start-at`, `--stop-after`,
  `--skip`), then `francli football status --env <env> --match-id <id> --details` until done.
  **Success = the main football pipeline SFN is all green** for the finished match. `--env` accepts custom stacks
  (e.g. `andrei`) as well as `dev` / `staging`.
- **wilson + football pipeline**: make the wilson-side change (API/lambda) on wilson's `dev` first, then run the pipeline on football's `mr_<iid>` (it reads the dev DB);
  the same env and check it is green.

Report evidence (request/response, invocation output, SFN status), not "it works".

### Missing files on dev: copy them from prod

A run on `dev` (or on a football `mr_<iid>`, which reads dev data) often fails because the match's files were
never copied to dev. Typical errors: missing match_infos, tracking or physical inputs. That's an **environment** failure, not the change. Fix it with `s3-copy`: the CLI installed by the GitLab project
`skillcorner/shared/migrate-and-copy` (`~/.local/bin/s3-copy`; if it's missing, `uv tool install migrate-and-copy` from the internal index). It invokes the prod lambda `wilson-data_copy_tool-prod`
(eu-central-1), which copies from `--origin-env` (default `prod`) to `--destination-env`. Copying to prod is refused.

```bash
s3-copy match-infos --destination-env dev --matches 941428,941429          # presets: match-infos, tracking-extrapolated,
s3-copy physical    --destination-env dev --matches 941428                 #   physical, physical-v301, dynamic-events,
                                                                            #   gi-served-by-api, gi-runs-events, copy-gt, …
s3-copy no-preset   --destination-env dev --matches 941428 \
  --skcr-keys "skcr-data:prod/<MATCH_NAME>/<MATCH_NAME>.mp4,skcr-football-data-raw-us:prod/<MATCH_NAME>/ball_positions.json"
```

- Pick the preset that matches the missing file; use `no-preset --skcr-keys BUCKET:PATH` (placeholders
  `<MATCH_ID>`, `<MATCH_NAME>`, no env in the bucket name) for anything else. Already-copied files are skipped
  unless you pass `--force`; don't pass it without a reason.
- It writes dev data, so ask the user first, unless a standing approval covers it. Then rerun only the
  affected steps: `qa_run.py <plan> --only <ids> --approved`.
- **Exception, `No video on S3`** (in `pipeline_checks_before_start`): usually the vidic-v2 `Video` row wasn't
  copied to dev. Recreate that row first, as described in hub `docs/no-video-on-s3-on-dev.md`. Copy the mp4 with
  `s3-copy no-preset` only for legacy/custom-video matches. Never use Forest's video actions on dev: they hit
  Vidic prod.
- `francli football tools migrate-and-copy` exists but is a stub (`NotImplementedError` in francli 1.61); use
  `s3-copy`.

## 5. Tear down

Once validated, destroy every custom stack you created:

```bash
uvx pirlo destroy --project-name <project> --env mr_1234 --dry-run
uvx pirlo destroy --project-name <project> --env mr_1234
```

Never pass `--force` (wipes data buckets irreversibly) unless asked. Never destroy `dev` / `staging`.

## 6. After merge: repin

The user merges the lib MRs (final versions get published). Then on each consumer branch: replace the prerelease
spec with the final version, `uv lock` everywhere it was pinned, commit, push. For son, this is often a follow-up
MR relocking lambdas.

## Guardrails

- Shared envs (`dev`, `staging`) and anything prod: confirm with the user every time.
- Only run targeted tests; never the full wilson suite, never `-n auto`.
- Write every MR description with the **`mr-description`** skill (fills the team template from the branch diff),
  both when opening the MR and after QA to add the validation section.
- Link every MR you open.
