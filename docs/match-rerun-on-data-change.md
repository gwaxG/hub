---
repo: [wilson]
mr: [wilson!2981, wilson!2829]
verified_at: 2026-11-26
source: https://app.notion.com/p/4226552a98c981848706de15a33da973
---

# Match rerun after a sensitive data change (wilson !2981, open)

State on 2026-11-27: MR open at head `81ff3035c`, lambda locked on son `0.105.0a4+andreimitriakov`, deployed on
wilson dev. QA at that head: API saves and the sweep pass (it relaunched `[2076621, 2070668]`, oldest first); the
DB reads (`rerun_flagged_at`, statuses) are still pending, see the MR description. Notion task 4412. Verify against the branch before use.

## Design

- A sensitive change stamps `DataCollection.rerun_flagged_at` (migration `0294_datacollection_rerun_flagged_at`,
  nullable) on every match except a `not_available` one. The status never changes. Stamping matches that are not
  `postmatch` yet keeps a change made while a run is in flight (first run, `to_rerun` relaunch): the sweep only
  relaunches `postmatch` matches, so it picks the match up when its run ends. Decided in review on 2026-11-27;
  the ticket first said "postmatch only".
- `TO_RERUN` stays an operator state. A sensitive change never sets it. A failed sweep run does: the classic
  `DataCollection`, or the `VideoDataCollection` of the failed custom feed, so operators see it in Gaffer and
  relaunch. `mark_matches_to_rerun` and its callers are unchanged.
- `son/rerun_schedule.py`:
  - `RerunSchedule(launch=...)`: `schedulable(match_ids)` (what `add` would stamp), `add(match_ids)` (callers run
    it on commit; each call restarts the wait) and `relaunch_due(has_time)` (postmatch rows older than
    `QUIET_PERIOD`, 2 h, oldest first; stops when `has_time()` is false, the matches left keep their schedule).
    It returns a `SweepResult` (relaunched and failed match ids). The launcher is injected, so tests pass a mock.
  - `MatchRerun(match).launch()`: the default launcher. One `PipelineRun` for the classic run (not for a
    custom-only match) and one per relaunchable custom feed, requester `rerun_flagged_matches_sweep`,
    `direct_launch=True`. It tries every run, hands a failed one to the operators, then raises once.
- `son/custom_feed_relaunch.py`: `get_relaunchable_custom_feed_types`, `get_custom_video_kwargs_for_relaunch` and
  `NOT_RELAUNCHABLE_STATUSES`, moved from `gaffer/core/match_launch.py` (which re-imports them). They only needed
  son, so the son-only lambda can now rerun custom feeds. Tests that patch S3 or Vidic for these functions must
  target `son.custom_feed_relaunch.*`.
- The sweep clears the timestamp before the launch, with a compare-and-set on the value it read. A newer
  change keeps its schedule. A failed launch is never retried (a match that always fails would loop).
- Lambda `pulumi/aws/management/rerun_flagged_matches`: EventBridge `rate(15 minutes)`, timeout 900 s,
  `maximum_retry_attempts: 0` (a retried async invoke would relaunch the same matches twice). Two sweeps can
  overlap; the compare-and-set claim launches a match once. It stops taking matches when under 3 min are left.
  It sets up Sentry (`SentryTracing`) and raises `RelaunchFailed` at the end when a relaunch failed. The CloudWatch
  alarm paulumi creates for an EventBridge lambda only watches failed invocations of the rule, not function
  errors, so Sentry is the alert channel.
- Any other launch consumes the schedule in `Match._mark_full_run_accepted`, once the launch lambda accepts the
  run and only for a timestamp older than the launch start. A rejected launch (`run_checks`) and a change made
  during the launch keep the schedule. A match with custom videos keeps it on any such launch (one run does not
  refresh all its outputs); only the sweep clears it. The same method resets the DE checks: on the `DataCollection` for a classic run, on
  the feed's `VideoDataCollection` for a custom feed run (a custom run does not regenerate the classic DE).

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
  by hand, after a DB backdate of `rerun_flagged_at` (more than the quiet period). Check what is due first: on
  2026-11-27 dev still has `2070668` and `2076621` stamped, so a sweep would start two football runs.
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

## Human review of 2026-11-27 (Marthe Brandam), open points

- Product alignment still to confirm: a rerun hides the DE of the match until its GI quality check (about 1 h),
  and for good if the run fails before it.
- Follow-up MRs, not in !2981: expose `rerun_flagged_at` on the Gaffer match response; gaffer-front wording
  (stadium modal still says "Update and relaunch", lineup save says nothing).
- The sweep calls `update_stadium` (a Heimspiel call) for each launch, as `relaunch_matches` does;
  `block_preprocessing_gate=True` was offered to the reviewer as an option.
- The dev Aurora (port 5432) is only reachable from the office network or the VPN. From a home network the
  Django shell fails with `OperationalError: connection timeout expired` while the dev API and AWS calls still
  work. Plan DB checkpoints for a day with that access, or run them before the sweep clears the stamps.
- GitLab resolves a diff thread by itself when a push changes its lines (shown as resolved by the pusher): four
  of the seven human threads closed that way; the other three stayed open for the reviewer.
- The local test Postgres container (`wilson-test-pg`) does not restart with the machine: `docker start
  wilson-test-pg` when tests fail with "connection refused" on 5432.

Related: [gaffer-lineup-swap-rerun](gaffer-lineup-swap-rerun.md),
[gi-v3-core-events-skipped-stale-gi](gi-v3-core-events-skipped-stale-gi.md),
[son-release-on-merge](son-release-on-merge.md).
