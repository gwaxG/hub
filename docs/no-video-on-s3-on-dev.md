# `No video on S3` for a match copied to dev

## Symptom

`pipeline_checks_before_start` (football SFN) fails with:

```
PipelineChecksFailedError: Pipeline checks failed for match <id> with 1 error(s):
 No video on S3
```

for a match that was "copied to dev" and plays fine on prod.

## Causal chain

`son/pipeline_checks/run_checks.py::run_checks` only reaches the video check when
the payload has no `video_id` and the first `Video` row for the match is not a
data-provider one (`sics`/`smrtstats`/`heimspiel`). It then calls
`launch_metadata_checks()` → `Video.objects.check_video_existence(match)`
(`son/models/video.py:85`).

That manager method branches on
`Match.get_video_from_vidic_v2()` — a **wilson DB lookup**:
`match.video_set.filter(vidic_version='v2').exclude(provider='custom')`.

* row found → queries Vidic for an active `video_files` record → `NoVideoActiveOnVidic` if missing.
* **no row** → falls back to the pre-Vidic legacy path
  `s3://{VIDEO_BUCKET_NAME}/prod/<match_unique_name>/<match_unique_name>.mp4`
  and raises `NoVideoOnS3` when it is absent.

On dev `VIDEO_BUCKET_NAME` is `skcr-algo-dev` (`settings_base.py:487`), and nothing
puts an mp4 there:

* `migrate-and-copy` / `wilson-data_copy_tool-prod` copies **S3 objects only** — no
  wilson DB rows, no Vidic records — and **no preset includes `<MATCH_NAME>.mp4`**.
* Vidic v2 keeps videos in `skcr-video*`, not `skcr-algo*`, so for a v2 match the
  legacy key usually does not exist even on prod.

So the real cause is a **missing `Video` row with `vidic_version='v2'` in the dev
wilson DB**; the S3 message is just the legacy fallback's error.

## Useful fact

Dev/staging/gi wilson all point at **Vidic prod** — `_vidic_env()`
(`settings_base.py:35`) returns `prod` for every env except `gaffer1-4`. So the
prod video *is* reachable from dev once the row exists.

## Fix

1. Recreate the `Video` row on dev (provider + feed type copied from prod), e.g.
   `Video.objects.create(match_id=..., provider=..., video_feed_type=..., vidic_version='v2', status='done', fps=10)`,
   then relaunch. The check then queries Vidic prod and passes.
2. Legacy/custom-video matches only: copy the mp4 explicitly —
   `no-preset --destination-env dev --matches <id> --skcr-keys "skcr-algo:prod/<MATCH_NAME>/<MATCH_NAME>.mp4"`.

**Do not** use the Forest *Add video* / *Replace video* actions on dev: they call
`vidic_client.import_video` / `create_video` / `video_set_status` against **Vidic
prod** and can 409 or deactivate the production video.
