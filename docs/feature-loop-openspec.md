---
repo: [hub]
mr: []
verified_at: 2026-11-22
---

# feature-loop on OpenSpec

`/feature-loop` writes its plan as **OpenSpec changes** instead of `plan.md`: one change per touched repo, same
kebab-case name (the ticket slug), in that repo's feature worktree at `openspec/changes/<change>/`. The change
ships in the MR and is archived into `openspec/specs/` at hand-off, so specs land with the code.

## Mechanics

- No `openspec/` in the repo → the skill runs `openspec init --tools none --no-animation .` in the worktree
  (creates only `openspec/config.yaml`, `specs/`, `changes/archive/`; `--tools none` because the OpenSpec skills
  are installed globally in `~/.agents/skills`, symlinked into `~/.claude/skills`), then overwrites
  `config.yaml` with `.claude/skills/feature-loop/openspec-config.yaml`.
- SkillCorner rules go through `config.yaml` (`context`, per-artifact `rules`, `operations.apply.guidance`), not
  a forked schema: verified on CLI 2.1.1 that they come back in `openspec instructions <artifact> --json`
  (`context`, `rules`) and `instructions apply --json` (`operationGuidance`). A fork
  (`openspec schema fork spec-driven <name>` → `openspec/schemas/<name>/`) would copy ~300 lines of upstream
  instructions into every repo and freeze them.
- Only the conductor runs explore / propose / update / archive (they ask the user); subagents read the change via
  `openspec instructions apply --json` and tick `tasks.md`.
- `openspec-explore` does not replace tech-explorer / football-explorer: it is a conversation with the user, with
  no fixed output, and it asks before every write, so a subagent can't run it. The loop uses it at the gate when a
  verdict isn't "clear" and on a "wrong understanding" restart, then `openspec-update-change` folds the decisions
  in. tech-explorer reads existing `openspec/specs/` instead (`openspec list --specs`, `openspec show`).
- Spec scenarios are the QA oracles: qa-planner writes one check per scenario, the verifier judges per scenario.

## Traps

- `openspec list --json` with no root exits non-zero and returns `"root": null` — that is the "not initialised"
  answer, not a broken CLI.
- `openspec new change` with no root creates `openspec/` as a side effect; init explicitly first.
- `status` is file-existence only: `tasks.md` present reads `done` even if `specs/` was never written.
- Stores (`openspec store setup`) exist for cross-repo specs; not used — per-repo roots keep specs in code review.
