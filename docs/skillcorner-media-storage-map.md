---
repo: [football-metadata-service, football-metadata-service-client, argocd, orion, orion-front, vidic-client]
mr: [football-metadata-service!24, football-metadata-service-client!10, argocd-platform-services-football-metadata-service!30, argocd-platform-services-football-metadata-service!32, football-metadata-service!29, argocd-platform-services-football-metadata-service!43]
verified_at: 2026-11-27
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
- **Daily job** `python -m app.ingestion` (prod cron `ingest-metadata`, 10:00 Paris; named `ingest-players` until argocd !30 merges): mirrors wilson competitions → teams → players through son, create-only, wilson id = FMS id, HEIMSPIEL matchings only (first claimant wins on duplicates). Pulls the image of each entity created in that run. Steps are isolated; exit 1 if one fails. `--limit` / `--matched-only` apply per entity type.
- **Weekly job** `python -m app.images` (prod cron `refresh-images`, Wednesdays 06:00 Paris, argocd !30): re-pulls every matched entity from the FMS DB (no son), writes only changed images (HEAD: size + CRC32 via skcr-utils `content_matches`, plus our `Cache-Control`; counted `unchanged`), sets flags, never clears them. Existing prod players get photos only from this job — trigger it once after the first deploy.
- **Read:** `GET /api/images/{player_photo|team_logo|competition_logo}/{id}` returns the image bytes (`image/jpeg|png`, `Cache-Control: private, max-age=3600`) or 404 `{"detail": "Absent from the provider."}`. Client: `get_image(ImageType, id) -> Image(content, content_type) | None`. Orion must proxy the bytes to its front (front auth is a Bearer header, so the front loads them as blobs, or Orion embeds a `data:` URI).
- **Why bytes, not presigned URLs (infra review on FMS !24, 2026-11-23):** a presigned URL carries the signer's access key id + session token, and the FMS IRSA role also reads SSM / Secrets Manager. Options weighed: API proxy (chosen: no credential, no infra), CloudFront + OAC (no credential but distribution, OAC, bucket policy, key group + private key in Secrets Manager, all in the FMS pulumi stack), dedicated read-only signing role. Cost ≈ $0.40 per 1M views in S3 GETs; one HEAD per image in the weekly job skips unchanged writes.
- **HEIMSPIEL gfx URLs** (`s.hs-data.com/gfx/...`, 100x100, no auth): a missing image answers **302 → /404.gif**, not 404. Fetch without following redirects; only 200 + `image/*` counts. Transport errors / 5xx / 429 = failed, not missing.

## Traps found while building it

- **If you presign S3 URLs elsewhere:** skcr-utils `S3Storage.generate_presigned_url` does a HEAD first (a missing object → 403 → 500), and a plain boto3 client presigns with SigV2, rejected by buckets created after mid-2020 (use `Config(signature_version='s3v4')`).
- **pirlo needs the full project path** for FMS: `skillcorner/software/football-metadata-service` (the bare name also matches the argocd chart project). `pirlo deploy --env dev` works for FMS; CI's update-helm opens and auto-merges the dev image bump in the argocd chart.
- **Running FMS jobs on dev:** the API pod (250m / 256Mi) OOMs on son, so never `kubectl exec` a job there. A deploy only changes the image: CronJobs come from the argocd chart values per env (`environments/<env>/values.yaml`, `fastapi-base.cronJobs`). argocd !32 adds `ingest-metadata` and `refresh-images` to dev as **suspended** CronJobs (`backoffLimit: 0`, `--limit 1000`); `fastapi-base` ≥ 0.3.1 supports `suspend` / `backoffLimit` per job.
- **Dev cron test workflow** (!32 merged 2026-11-20; tested with `--limit 100`): (1) `pirlo deploy --project-name skillcorner/software/football-metadata-service --branch <branch> --env dev`; (2) run a job from a suspended CronJob with plain kubectl (`AWS_PROFILE=Production.Skcr-Software-Common-Role`, kube context `workloads-prod`):
  ```bash
  NS=football-metadata-service-dev
  # as defined (--limit 1000); use ...-ingest-metadata for the daily job
  kubectl create job --from=cronjob/$NS-refresh-images refresh-images-manual-$(date +%s) -n $NS
  # other limit: rewrite the value in the rendered Job (the command list renders it as - "1000")
  kubectl create job --from=cronjob/$NS-ingest-metadata ingest-metadata-manual-$(date +%s) -n $NS \
    --dry-run=client -o yaml | sed 's/- "1000"/- "100"/' | kubectl create -f -
  kubectl get jobs -n $NS; kubectl logs -f job/<job-name> -n $NS
  ```
  `uv run workflows/fms_dev_cron.py <ingest-metadata|refresh-images> [-- <job args>]` wraps the same steps, waits for the Job and exits non-zero on failure. Arguments after `--` replace the CronJob's own (`-- --limit 100`, `-- --type team_logo --competition 37`).
- **FMS client locally without installing:** `uv run --no-project --python 3.13 --index internal=https://pypi.skillcorner.com/pypi/internal/simple/ --with 'football-metadata-service-client==<version>' --with httpx python …`. `--python 3.13` is required: uv otherwise picks free-threaded 3.14t, where `orjson` (via fitrequest) fails to build. `FootballMetadataServiceClient(env='dev')` uses M2M auth from SSM (needs the AWS profile). A pirlo prerelease of the client is `X.Y.Za0+<user>` built from the current pyproject version, so it sorts *below* the released `X.Y.Z` — pin it exactly.
- **FMS API on dev:** the gateway needs a Cognito JWT even for `/api/health`. Use `kubectl port-forward svc/football-metadata-service-dev` plus the `X-User-Sub` header.
- **QA runner gap:** `~/.claude/agents/qa/qa_run.py` has no shell/SQL step and cannot send custom headers, so FMS QA ran as manual steps.

- **A missing key answers 403 / `AccessDenied`**, not 404, because the IRSA role has no `s3:ListBucket` (HEAD → `403`, GET → `AccessDenied`); FMS reads both as absent.
- **fitrequest generated methods** drop the response content type and raise on 404; the client's `get_image` is written by hand on `self.session.synchronous` with `self.session.base_url` (that httpx client has no base_url).
- **HEIMSPIEL re-encodes player photos on a CDN miss:** after Cloudflare's 4 h cache expires, the origin may return different bytes for the same photo, so a weekly refresh still rewrites part of the photos (dev QA: 73/93, then 0/93 with a warm cache). Logos were stable.

## Task 4435: images stored by HEIMSPIEL id (FMS !29, chart !43, open drafts 2026-11-27)

Ticket: https://app.notion.com/p/4236552a98c980d99e12e3076fa91312. It replaces the task 4293 logic above once !29 merges; QA passed on dev (capped to co37, co19, co73).

- **Why:** FMS matchings were a create-only snapshot of wilson, and images were keyed by our id. A matching fixed or removed in wilson, or a merged duplicate, never reached FMS.
- **Keys:** `assets/heimspiel/player/photo/{person_id}.jpg`, `assets/heimspiel/team/logo/{team_id}.png`, `assets/heimspiel/competition/logo/{competition_id}.png` (bare digits). The old keys and the `has_*` columns stay, unread and unwritten, until the Hub switch.
- **Weekly job** `python -m app.images [--type T] [--competition ID ...]` lists from HEIMSPIEL through data-provider-clients (≥ 1.14.0 for `is_placeholder`), no DB and no son:
  - logos of every football competition (`/competition-list/`, sport id 1) and of its non-placeholder teams (`/teams-by-season/co{id}/`);
  - photos of the `role.group == 'Athletes'` squad entries (`/team-squad/te{id}/`, id = `person.id`) of `settings.HEIMSPIEL_PHOTO_COMPETITION_IDS` (the 20 contract ids; 9 extension ids wait for the contract);
  - `--competition` replaces the scope of the logos; photos are always intersected with the contract list;
  - each feed is read once per run, retried once, and a failure makes the job exit 1 without stopping the run; nothing is deleted from S3;
  - log lines `Photo report competition=co37 in_scope=… with_photo=… without_photo=… failed=…` and `Photo report total distinct_persons=… feed_failures=N` give the counts for the contract owner.
- **Read:** `GET /api/images/{type}/{our_id}` resolves our id through the FMS HEIMSPIEL matching row at request time. No row or no object → the same 404. The client contract is unchanged.
- **Matching sync:** each entity step of the daily `python -m app.ingestion` now reconciles the HEIMSPIEL matchings with wilson: one DELETE of removed and changed rows, then one INSERT, in one transaction (swapped ids cannot collide). A competition with several HEIMSPIEL ids keeps the earliest wilson matching. An empty wilson read with rows in FMS fails the step. Entity creation stays create-only; ingestion no longer pulls images. A fix in wilson shows after the next run (≤ 24 h).
- **Rollout:** after the prod deploy every image answers 404 until both jobs have run once; run them by hand. Merge chart !43 with the image (`--limit` no longer exists on `app.images`).

Facts measured on 2026-11-27:

- `/competition-list/`: 234 football competitions (212 club, 22 national, 61 female), 3 basketball, 2 American football. 58 of the 234 have no logo.
- **"No season logic" has a cost:** `/teams-by-season/co{id}/` returns HEIMSPIEL's current season only. MLS (co73) returned its 18 playoff clubs, not 30. The product owner accepted this.
- Champions League (co19) lists the 36 league-phase clubs; 5 were outside the contract countries. All are in the photo scope (decision).
- Photo coverage: co37 521 of 542, co19 1,067 of 1,197, co73 232 of 589. About 29 athletes per squad, so about 10,000 persons for the 20 leagues.
- **The JSON feeds answer without credentials.** The FMS IRSA role cannot read `/HEIMSPIEL_USERNAME` / `/HEIMSPIEL_PASSWORD` (eu-central-1); dpc logs `Unable to retrieve AWS variable` twice and the calls still succeed.
- Not run before prod: the uncapped listing (all 234 competitions for team logos, the 20 contract competitions for photos).
- Follow-ups: enrichment keeps the old person's data after a matching change; nobody reads the images yet (see below); what the 12,000-photo cap counts is a question for the contract owner.

QA and CI traps:

- `uvx pirlo` fails on this machine (uv picks free-threaded 3.14t, `orjson` does not build); use the installed `~/.local/bin/pirlo`.
- The kube context is `andrei_mitriakov@workloads-prod.us-east-1.eksctl.io`, not `workloads-prod`.
- Finished Jobs are garbage-collected after a few minutes: save `kubectl logs job/…` at once.
- `kubectl exec` into the API pod truncates large stdout; run feed scripts locally with dpc. Wait more than 3 s after `kubectl port-forward` before the first request.
- FMS CI lints with the latest ruff and `prek` (`pretty-format-json` on fixtures), newer than the locked ruff: run `uvx ruff check --no-fix` and `uvx prek run --all-files` before the push.
- The FMS mirror's `origin` is https without credentials: fetch and push with the SSH URL.

## What orion takes today

- Orion schemas declare nullable `logo_url`, `team_logo_url`, `competition_logo_url`, `photo_url`. Repositories still set them to null (TODO "no source yet"). Wiring them to FMS `get_image` is the next step, outside task 4293's FMS scope.
- Only the user `avatar` carries a real value, from Cognito.
- orion-front flags are static `flag-icons` SVGs bundled under `/assets/flags/`; the bundle is served from `skcr-orion-{env}` behind CloudFront (SPA router function; `/api/*`, `/admin`, `/auth/*` go to the backend uncached).
