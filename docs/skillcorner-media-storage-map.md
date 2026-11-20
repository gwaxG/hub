---
repo: [football-metadata-service, football-metadata-service-client, argocd, orion, orion-front, vidic-client]
mr: [football-metadata-service!24, football-metadata-service-client!10, argocd-platform-services-football-metadata-service!30]
verified_at: 2026-11-20
source: https://app.notion.com/p/41b6552a98c980beb00dfdcb2d140dca
---

# Media storage and access map (Nov 2026)

Where images and video live in SkillCorner, how HEIMSPIEL images are stored and served, and what orion receives.

## Video

- Match videos live in S3 buckets `skcr-algo-*`. `vidic-client` (v2) reads them through presigned URLs (`#t={start},{end}` for a time range; clip sidecars with `include_sidecars=True`). Orion does not call vidic.

## HEIMSPIEL images in football-metadata-service (Notion task 4293)

Status 2026-11-20: FMS !24, client !10, argocd !30 open as drafts; QA passed on dev.

- **Access rule (contract, confirmed by Mohamed):** internal storage allowed; only authenticated Orion clients may see the images; no public access, no public API.
- **Buckets:** `skcr-football-metadata-dev` / `-prod` (us-east-1, private). IAM on FMS main grants Put/GetObject only under `assets/*`, to one IRSA role shared by the API pod and the CronJobs.
- **Keys (wilson id):** `assets/player/photo/{id}.jpg`, `assets/team/logo/{id}.png`, `assets/competition/logo/{id}.png`. Flags: `player.has_photo`, `team.has_logo`, `competition.has_logo`.
- **Daily job** `python -m app.ingestion` (prod cron `ingest-players`, 10:00 Paris): mirrors wilson competitions → teams → players through son, create-only, wilson id = FMS id, HEIMSPIEL matchings only (first claimant wins on duplicates). Pulls the image of each entity created in that run. Steps are isolated; exit 1 if one fails. `--limit` / `--matched-only` apply per entity type.
- **Weekly job** `python -m app.images` (prod cron `refresh-images`, Wednesdays 06:00 Paris, argocd !30): re-pulls every matched entity from the FMS DB (no son), overwrites, sets flags, never clears them. Existing prod players get photos only from this job — trigger it once after the first deploy.
- **Read:** `GET /api/images/{player_photo|team_logo|competition_logo}/{id}`, always 200 `{url, expires_at, detail}`; absent → `detail: "Absent from the provider."`. Client: `get_image(ImageType, id)`.
- **HEIMSPIEL gfx URLs** (`s.hs-data.com/gfx/...`, 100x100, no auth): a missing image answers **302 → /404.gif**, not 404. Fetch without following redirects; only 200 + `image/*` counts. Transport errors / 5xx / 429 = failed, not missing.

## Traps found while building it

- **skcr-utils `S3Storage.generate_presigned_url` does a HEAD** before signing (one S3 call per read; a missing object raises 403 without ListBucket → 500). Sign locally with boto3 instead.
- **A plain boto3 S3 client presigns with SigV2** (`AWSAccessKeyId=…&Signature=…`), rejected by buckets created after mid-2020. Use `Config(signature_version='s3v4')`.
- **pirlo needs the full project path** for FMS: `skillcorner/software/football-metadata-service` (the bare name also matches the argocd chart project). `pirlo deploy --env dev` works for FMS; CI's update-helm opens and auto-merges the dev image bump in the argocd chart.
- **Running FMS jobs on dev:** dev has no CronJobs, and the API pod (250m / 256Mi) OOMs on son. Run a one-off Job from the deployed image with the dev service account and 4Gi (`football-metadata-service-dev` namespace, cluster `workloads-prod`).
- **FMS API on dev:** the gateway needs a Cognito JWT even for `/api/health`. Use `kubectl port-forward svc/football-metadata-service-dev` plus the `X-User-Sub` header.
- **QA runner gap:** `~/.claude/agents/qa/qa_run.py` has no shell/SQL step and cannot send custom headers, so FMS QA ran as manual steps.

## What orion takes today

- Orion schemas declare nullable `logo_url`, `team_logo_url`, `competition_logo_url`, `photo_url`. Repositories still set them to null (TODO "no source yet"). Wiring them to FMS `get_image` is the next step, outside task 4293's FMS scope.
- Only the user `avatar` carries a real value, from Cognito.
- orion-front flags are static `flag-icons` SVGs bundled under `/assets/flags/`; the bundle is served from `skcr-orion-{env}` behind CloudFront (SPA router function; `/api/*`, `/admin`, `/auth/*` go to the backend uncached).
