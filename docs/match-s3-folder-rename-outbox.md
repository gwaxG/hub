---
repo: [wilson]
mr: [wilson!2908]
verified_at: 2026-11-18
source: [https://app.notion.com/p/41a6552a98c98106b3d8de48e283cadc]
---

# Match S3 folder rename via SQS + lambda (task 4245)

`Match.unique_name` (`YYYYMMDD_home_away`, computed from `date_time` + team `short_name`, not stored) keys
`prod/<unique_name>/` in `skcr-algo*`. Gaffer edits and the Heimspiel metadata update (an ECS task) changed it
without moving the folder, orphaning data (matches 2081836, 2075741, historical_v4 relaunch failed). It was never
implemented, not a regression (Forest had a shaky version).

**Design (wilson !2908, son 0.101.0):** `MatchS3RenamePublisher.publish(match, old_name)` (son) after the save in
Gaffer `match_update_serializer` and Heimspiel `_update_match_metadata_from_provider`; `transaction.on_commit` sends
`{old_match_name,new_match_name,new_match_date_time}` to FIFO queue `wilson-match-s3-rename-<env>.fifo`, group id =
match id (ordered A->B, B->C), random dedup id. The existing `edit_match_name_s3` lambda consumes it (`triggers.sqs`,
batch 1; handler accepts `Records` or a direct payload, raises on non-200; maxReceiveCount 3 (retries keep the FIFO group blocked, so order holds; a
failure reaches the DLQ after up to ~90 min), then the DLQ, which has an alarm and is checked by the data readiness probe (`s3_rename` module, `s3_rename_dlq`, reads the
queue attributes because SQS stops emitting metrics for an idle queue)). Queue/DLQ/alarm in `pulumi/01_infrastructure/match_s3_rename_queue.py`; the ECS task role gets
`sqs:GetQueueUrl`/`SendMessage` (`role_policies.py`). Visibility timeout 1800 = 6x the lambda timeout.

Trap: a Gaffer PUT that renames the match AND edits the timeline writes `periods_start_frames.json` inside the
transaction. It must target the OLD folder (`write_period_starts_to_s3(..., match_folder=old_unique_name)`), else the
post-commit copy from old to new overwrites the fresh file with the old frames.

Known gaps (accepted): a source folder missing is a 200 no-op (normal for unprocessed matches), so after A->B
dead-letters, B->C silently does nothing; two concurrent edits of one match can send out of commit order. Recovery =
move the folder to the current DB name.

History: sync lambda call in the request (504 on Gaffer) and an outbox table drained by an ECS task were tried first;
the team (Marthe) prefers queue + lambda (native retries + DLQ, where the stack is heading).

**Traps / gaps**
- The lambda reports failures in the payload (`errorMessage`, `statusCode` 400 on equal names) for direct callers;
  the SQS path converts them into exceptions.
- Send happens after commit: if SQS is down the edit stays and an `operation_error` is logged (no outbox, move lost).
- A DLQ message blocks nothing else, but later moves of that match find the old folder empty (no-op 200): replay the
  DLQ message in order.
- Model `Meta` must inherit `BaseModel.Meta` (`app_label='api'`) for any new son model (not needed here any more).
- `short_name` is a real field, empty in test fixtures: set it to test a team-change rename.
- Run Django with `uv run python server/manage.py` from the wilson root + `AWS_PROFILE=Production.Skcr-Software-Common-Role`.
- Forest and Django admin edits are not covered.
