---
repo: [wilson, son, vidic]
mr: [wilson!2540]
verified_at: 2026-11-03
---

# Validating match creation changes on dev

Recipe used for wilson !2540 ([heimspiel-lineups-wilson-flow](heimspiel-lineups-wilson-flow.md)).
Scripts live in wilson `.notebooks/mr_validations/2540/` (not shipped): `common.py` helpers,
`step_X_Y.py` (prep, dry run unless `--apply`) + `step_X_Y_validation.py` (read-only, exit 0 PASS /
1 FAIL / 2 WAITING), `weekend_recap.py`, `prerelease/prep.py` + `prerelease/validate.py`.

## Environment facts

- **Dev and staging write to prod Vidic** (only gaffer1–4 have their own Vidic:
  `pulumi/02_compute/wilson.py` `_wilson_env_var_extras`, settings_base `_vidic_env`). Any Vidic
  push from dev overwrites prod video events — choose test matches accordingly (never OBOS/SmrtStats,
  which hold operator Gaffer instructions).
- **Dev crons are off by default**: EventBridge schedules exist only for envs in
  `ENABLE_EVENT_BRIDGE` (`pulumi/02_compute/wilson.py`, `{'prod', 'teamapp'}`). Adding `dev` in a
  temporary commit turns them on; revert before merge.
- Run scripts from `wilson/server` with `SKILLCORNER_ENV=dev uv run python <script>`.

## Triggering the CE crons by hand

```bash
aws lambda invoke --function-name wilson-create_matches_from_provider_for_c-dev \
  --invocation-type Event --payload '{"competitionedition_id": 1635}' \
  --cli-binary-format raw-in-base64-out /dev/null
```

(Heimspiel: `wilson-create_matches_from_heimspiel_for_-dev`.) **Always pass
`competitionedition_id`**: with `{}` `task_by_row_v2` takes the due CE with the oldest `last_try`
— any CE (it picked OBOS 1415 by mistake once). A run processes the whole CE (~10 min for 190–380
matches): creates missing matches, retries every incomplete one, pushes Vidic where needed.
Running invocations can't be cancelled and the SSO role can't `PutFunctionConcurrency`.

With schedules on, forcing = set `<cron>_last_try` on `CompetitionEditionBeating` to an old date
(`configure_ce`/`force_crons` in `common.py`); "cron passed" = `last_try` moved, which is the
**start** of a run, not its end — check the lambda logs before validating.

## Preparing a scenario

- The crons only revisit **incomplete** matches: to re-run a step, make the match incomplete in a
  way the completion check sees (delete a **starter**, not a bench player; delete periods; delete
  the match). Unprotect first (`unprotect` in `common.py`).
- Delete a whole match with `delete_pick` (keeps the matchings in state to find the recreated one).
- TPM writes on a `skillcorner` lineup need `overwrite_manual_data=True`.
- Setting fields directly in the DB does not reproduce operator tools (they also flip
  `lineup_provider` to `skillcorner`).

## Checking Vidic without writing

Run the real `push_match_events_to_vidic(match, video)` with
`patch.object(vidic_client, 'write_events', side_effect=capture)` to get the payload Wilson would
send, then compare with `resolve_vidic_video(video, include_events=True,
by_provider_match_id=True)` on `period_events`/`instruction_events` (keys of the payload, floats to
0.1 s), plus `status_vidic_events == 'done'` on the video provider's MCS.

## Prerelease matrix used for !2540 (all passed 2026-11-03)

| Case | CE | Proves |
|---|---|---|
| V1 periods + Heimspiel subs deleted | 1574 League One (HS lineups on) | inline HS retrieval in the SICS periods pass + full Vidic push |
| R1 match deleted | 1635 Serie A (HS creation on, lineups off) | SICS flow unchanged, HS lineup steps ignored |
| R2 match deleted | 1729 PL (SICS only) | SICS flow unchanged, no HS status |
| R3 operator lineup minus a starter | 1635 | lineup untouched, SICS step `ignored`/`existing_lineup_kept` |

A "HS recreates subs → flag → SICS pushes" case was impossible on dev data: every League One match
had as many Heimspiel instructions as Vidic, so the count-only re-check skips the push.

## Local tests

`SKILLCORNER_ENV=ci DJANGO_SETTINGS_MODULE=wilson.settings_test DJANGO_CONFIGURATION=WilsonTest uv run
pytest <file> --migrations` — needs `docker start pg_skilldata` and a valid AWS session (settings
read SSM at import). Never the full suite, never `-n auto`.
