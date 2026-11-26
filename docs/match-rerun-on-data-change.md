---
repo: [wilson]
mr: [wilson!2981, wilson!2829]
verified_at: 2026-11-26
source: https://app.notion.com/p/4226552a98c981848706de15a33da973
---

# Match rerun after a sensitive data change (wilson !2981, open)

State on 2026-11-26: MR open at head `f35b9e2ab`, deployed on wilson dev and QA'd there (results in the MR
description). Lambda locked on son `0.105.0a3+andreimitriakov`. Notion task 4412. Verify against the branch before use.

## Design

- A sensitive change on a `postmatch` match stamps `DataCollection.rerun_flagged_at` (migration
  `0294_datacollection_rerun_flagged_at`, nullable). The status never changes. Matches in `''`,
  `not_available` or `to_rerun` are left untouched.
- `TO_RERUN` stays an operator state. The new path does not use it, and `mark_matches_to_rerun` and its
  callers (e.g. `replace_match_team`) are unchanged.
- `son/rerun_schedule.py` holds two classes:
  - `RerunSchedule(launch=...)`: `add(match_ids)` (callers run it on commit; each call restarts the wait) and
    `relaunch_due()` (postmatch rows with `rerun_flagged_at` older than `QUIET_PERIOD`, 3 h). The launcher is
    injected, so tests pass a mock.
  - `MatchRerun(match).launch()`: the default launcher. It launches the classic run (not for a custom-only match)
    and one run per relaunchable custom feed, requester `rerun_flagged_matches_sweep`, `direct_launch=True`. It
    tries every run, then raises `RerunLaunchError` once.
- `son/custom_feed_relaunch.py`: `get_relaunchable_custom_feed_types`, `get_custom_video_kwargs_for_relaunch` and
  `NOT_RELAUNCHABLE_STATUSES`, moved from `gaffer/core/match_launch.py` (which re-imports them). They only needed
  son, so the son-only lambda can now rerun custom feeds. Tests that patch S3 or Vidic for these functions must
  target `son.custom_feed_relaunch.*`.
- The sweep clears the timestamp before the launch, with a compare-and-set on the value it read. A newer
  change keeps its schedule. A failed launch is logged and never retried.
- Lambda `pulumi/aws/management/rerun_flagged_matches`: EventBridge `rate(1 hour)`, `maximum_retry_attempts: 0`
  (a retried async invoke would relaunch the same matches twice).
- Any other launch consumes the schedule in `Match._mark_full_run_accepted`, once the launch lambda accepts the
  run and only for a timestamp older than the launch start. A rejected launch (`run_checks`) and a change made
  during the launch keep the schedule. A match with custom videos keeps it on any such launch (one run does not
  refresh all its outputs); only the sweep clears it. The same method resets the DE checks.

## Callers (all stopped relaunching inline)

- Gaffer match save: `sync_match_lineup` returns True on any sheet change (add, remove, edit of jersey number
  or sheet position). An identical resave does not restart the wait.
- Gaffer stadium update: honours `is_relaunching_matches`; the response is always `200` / `updated` with an
  empty launch summary (the `202` / `updated_pipelines_pending` path is gone). The preview lists postmatch
  matches only (`get_schedulable_impacted_match_ids`).
- `merge_teams` command: no longer sets `TO_RERUN`; it schedules on commit, so a dry run schedules nothing.
- Forest player duplicate removal: reports "scheduled to rerun".

## Traps found during the rebase and the !2829 merge-in

- `TO_RERUN` flag and scheduling are mutually exclusive. The old !2829 flag (`flag_rerun_after_lineup_change`)
  flips the status inside the transaction, so the on-commit schedule finds no `postmatch` row and the sweep
  never relaunches. That is why only the DE checks reset and the tests were ported from !2829.
- Lambda son pin: the lambda locks the son prerelease (`0.105.0a1+andreimitriakov`), `pyproject.toml` says
  `son>=0.104.1` like the sibling lambdas. Lock recipe that leaves a clean lock: `uv lock --prerelease=allow -P
  'son==<prerelease>'`, then `uv lock --prerelease=if-necessary-or-explicit` (removes the `[options]
  prerelease-mode` block, keeps the prerelease). Repin on the released son after the merge.
- The sweep does not re-time the timeline from Vidic before a rerun; Gaffer `relaunch_matches` does.
- Migration numbers move: main took 0291, 0292 and 0293 while the branch was open. Renumber and repoint
  `dependencies` on each rebase; run the tests with `--create-db` after (also without `-n`: the single-process
  test DB is a separate database and keeps the old migration name).
- **Dev DB after a renumber:** dev had applied the migration as `0293_datacollection_rerun_flagged_at`. A plain
  rename of the `django_migrations` row is not enough when a new dependency (`0293_physical_v4_csv_ready`) is not
  applied yet: Django raises InconsistentMigrationHistory. Done on 2026-11-26 with the branch code against the
  dev DB: delete the old row, `migrate api 0293_physical_v4_csv_ready` (no SQL), then
  `migrate api 0294_datacollection_rerun_flagged_at --fake`.
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
  retried the invoke; the retry returned `[]` (compare-and-set held), so `qa_run.py` reported a false failure.
  Invoke with `AWS_MAX_ATTEMPTS=1 aws lambda invoke --cli-read-timeout 600 ...` to get the real answer.
- `qa_run.py` steps copied into another plan keep their `requires`; a step whose requirement is not in the plan is
  skipped silently unless you read its result file.
- `francli football status --start <ts>` returned `[]` right after the launch; list with `--all-runs` and filter on
  requester `rerun_flagged_matches_sweep`.
- Dev matches used: 2070668 (postmatch, NCAA, substitutions, green pipeline), 2076621 (postmatch, only match in
  the stadium 8206 window from 2026-08-16), 2095661 (prematch). Both postmatch matches stay stamped on dev.
- `lint-mr-title` (required job) rejects a `[proposal]` prefix: the MR title must start with the Conventional
  Commit type. The job reads the title at pipeline creation, so start a new MR pipeline after a retitle.
- **Full-row saves erase the stamp.** `rerun_flagged_at` lives on `DataCollection`, so any `data_collection.save()`
  on an instance loaded earlier writes the old value back (it can drop a new schedule or restore a cleared one).
  The Gaffer match save now uses `save(update_fields=[...provider fields, 'updated_at'])`. Note
  `BaseModel.save(update_fields=[])` (empty list) does a full save. Other full saves of `DataCollection` (pipeline
  status writers once they run on son >= 0.105) have the same hazard and were not audited.
- CodeRabbit reviews each push again and opened a second round of four threads on the fix commits; plan for it.
- Review threads: CodeRabbit summary comments are plain notes; a reply turns each into a thread that can be
  resolved. The Pulumi preview bot edits its note and reopens its thread on every pipeline. The summary comment
  can hold nitpicks that have no thread of their own.
- Lineup sync sub-state flip (`was_sub != now_sub` deletes the player's events) must use the sheet view too. With
  the stored role, a substitute who came on flipped on every save; without `timeline` in the payload the events
  were not written back. A save without `timeline` still resets stored playing times (behaviour on main).
- `QA_API_USER` / `QA_API_PASSWORD` are exported in `~/.bashrc`, which a non-interactive shell does not load.

Related: [gaffer-lineup-swap-rerun](gaffer-lineup-swap-rerun.md),
[gi-v3-core-events-skipped-stale-gi](gi-v3-core-events-skipped-stale-gi.md),
[son-release-on-merge](son-release-on-merge.md).
