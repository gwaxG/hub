---
repo: [wilson]
mr: [wilson!2981, wilson!2829]
verified_at: 2026-11-26
source: https://app.notion.com/p/4226552a98c981848706de15a33da973
---

# Match rerun after a sensitive data change (wilson !2981, open)

State on 2026-11-26: MR open, deployed and QA'd on wilson dev at `8d7b435b8` (results in the MR description).
Notion task 4412. Verify against the branch before use.

## Design

- A sensitive change on a `postmatch` match stamps `DataCollection.rerun_flagged_at` (migration
  `0293_datacollection_rerun_flagged_at`, nullable). The status never changes. Matches in `''`,
  `not_available` or `to_rerun` are left untouched.
- `TO_RERUN` stays an operator state. The new path does not use it, and `mark_matches_to_rerun` and its
  callers (e.g. `replace_match_team`) are unchanged.
- `son/rerun_schedule.py` holds both sides:
  - `schedule_postmatch_matches_for_rerun(match_ids)`: callers run it on commit. Each call restarts the wait.
  - `relaunch_quiet_scheduled_matches()`: relaunches `postmatch` rows with `rerun_flagged_at` older than
    `QUIET_PERIOD` (3 h), requester `rerun_flagged_matches_sweep`, `direct_launch=True`.
- The sweep clears the timestamp before the launch, with a compare-and-set on the value it read. A newer
  change keeps its schedule. A failed launch is logged and never retried.
- Lambda `pulumi/aws/management/rerun_flagged_matches`: EventBridge `rate(1 hour)`, `maximum_retry_attempts: 0`
  (a retried async invoke would relaunch the same matches twice).
- Any launch (`Match.launch_football_pipeline`) clears `rerun_flagged_at`.

## Callers (all stopped relaunching inline)

- Gaffer match save: `sync_match_lineup` returns True on any sheet change (add, remove, edit of jersey number
  or sheet position). An identical resave does not restart the wait.
- Gaffer stadium update: honours `is_relaunching_matches`; the response is always `200` / `updated` with an
  empty launch summary (the `202` / `updated_pipelines_pending` path is gone). The preview lists postmatch
  matches only (`get_schedulable_impacted_match_ids`).
- `merge_teams` command: no longer sets `TO_RERUN`.
- Forest player duplicate removal: reports "scheduled to rerun".

## Traps found during the rebase and the !2829 merge-in

- `TO_RERUN` flag and scheduling are mutually exclusive. The old !2829 flag (`flag_rerun_after_lineup_change`)
  flips the status inside the transaction, so the on-commit schedule finds no `postmatch` row and the sweep
  never relaunches. That is why only the DE checks reset and the tests were ported from !2829.
- Lambda son pin: the lambda locks the son prerelease (`0.105.0a1+andreimitriakov`), `pyproject.toml` says
  `son>=0.104.1` like the sibling lambdas. Lock recipe that leaves a clean lock: `uv lock --prerelease=allow -P
  'son==<prerelease>'`, then `uv lock --prerelease=if-necessary-or-explicit` (removes the `[options]
  prerelease-mode` block, keeps the prerelease). Repin on the released son after the merge.
- The sweep passes no custom video arguments. The old Forest action also relaunched custom video feeds
  (`get_custom_video_kwargs_for_relaunch`); the sweep does not appear to.
- Migration numbers move: main took 0291 and 0292 while the branch was open. Renumber and repoint
  `dependencies` on each rebase; run the tests with `--create-db` after.
- `cicd/lambda-builds.yml` header count conflicts on each rebase: set it to the real `build:lambda` job count.

## QA on dev (2026-11-26), what it taught

- **Change detection defect, fixed in `8d7b435b8`.** The first version compared the stored TPM (number, role,
  start/end time) with the sheet baseline from `_times_for`. The timeline sync rewrites playing times and the entry
  role after the lineup sync, so on a match with substitutions every save looked like a change and restarted the
  wait. The fix compares the sheet view: `number` and `SUB if start_time != 00:00 else role acronym`, the rule of
  `LineupPlayerSerializer.get_position`. Unit tests with a goalkeeper and no substitution did not catch it.
- No endpoint exposes `rerun_flagged_at` or the DE checks: check them with a Django shell on the dev DB
  (`SKILLCORNER_ENV=dev DJANGO_SETTINGS_MODULE=wilson.settings_local .venv/bin/python server/manage.py shell`).
- The EventBridge schedule exists on prod only. On dev, invoke `wilson-rerun_flagged_matches-dev` (eu-central-1)
  by hand, after a DB backdate of `rerun_flagged_at` (more than 3 h).
- Sweep cold start: Lambda init hits the 10 s init limit, the first invoke took 57 s. boto3's 60 s read timeout
  retried the invoke; the retry returned `[]` (compare-and-set held), so `qa_run.py` reported a false failure. Trust
  the lambda log line `Relaunched N scheduled matches` and the DB, or raise the client read timeout.
- `francli football status --start <ts>` returned `[]` right after the launch; list with `--all-runs` and filter on
  requester `rerun_flagged_matches_sweep`.
- Dev matches used: 2070668 (postmatch, NCAA, substitutions, green pipeline), 2076621 (postmatch, only match in
  the stadium 8206 window from 2026-08-16), 2095661 (prematch). Both postmatch matches stay stamped on dev.
- `lint-mr-title` (required job) rejects a `[proposal]` prefix: the MR title must start with the Conventional
  Commit type.
- `QA_API_USER` / `QA_API_PASSWORD` are exported in `~/.bashrc`, which a non-interactive shell does not load.

Related: [gaffer-lineup-swap-rerun](gaffer-lineup-swap-rerun.md),
[gi-v3-core-events-skipped-stale-gi](gi-v3-core-events-skipped-stale-gi.md),
[son-release-on-merge](son-release-on-merge.md).
