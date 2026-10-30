---
repo: [wilson]
mr: []
verified_at: 2026-10-30
---

# Find a client's IP addresses by username (wilson prod)

No single log has both *who* and *from where*:

| Source | Has user | Has real client IP | Retention |
|---|---|---|---|
| CloudWatch `wilson-prod` (`request_log` lines) | yes (`user_info.username`, `user_id`) | no | 365 d |
| CloudFront access logs `s3://skcr-files-prod/cf-logs/` | no (only `token=` query param if the client uses it) | yes (`c-ip`) | ~1 week |
| ALB access logs `s3://logs-from-aws/load-balancer/ecs-prod/` | no | **no** — client is CloudFront edge; ALB logs don't keep `X-Forwarded-For` | — |
| `auditlog_logentry.remote_addr` | yes | yes | only on writes to `User`, `Group`, `UploadAuthorization` |

So the workflow is: get the user's requests (timestamp + endpoint + params) from
CloudWatch, then join them to CloudFront logs on time + path + query string.

## Why the request log has no IP

`api/middleware.py::RequestLoggerMiddleware` → `get_extra()` logs params, endpoint,
method, referer, user agent, body (redacted) and user info — never `REMOTE_ADDR`.
Logger `request_tracking` has no handlers but propagates to root `console_json`
→ stdout → ECS → CloudWatch. Its `user_agent` is always `Amazon CloudFront`
(the ALB/CloudFront hop), so the real UA is only in CloudFront logs too.

`AuditlogMiddleware` (same file) does capture the IP (first `X-Forwarded-For`),
but only lands in DB when an audited model changes.

## Steps

AWS profile `Production.Skcr-Software-Common-Role`, region `eu-central-1`.

1. **CloudWatch Logs Insights** on log group `wilson-prod` (streams `app-prod/…`
   and `physical-prod/…`), last N days:

   ```
   fields @timestamp, endpoint, method, params.match.0, status_code
   | filter message = "request_log" and user_info.username = "<email>"
   | sort @timestamp asc
   ```

   Note the UTC hours that contain requests (`@timestamp` is UTC).

2. **Pull CloudFront logs** for those hours only. Prod distribution is
   `E2XLBJ13K3RVLX` (skillcorner.com); files are flat under the prefix, named
   `E2XLBJ13K3RVLX.YYYY-MM-DD-HH.<hash>.gz` (UTC hour). Don't list the whole
   prefix — it goes back to 2018 and times out; filter with `--prefix`:

   ```bash
   P=Production.Skcr-Software-Common-Role
   aws s3api list-objects-v2 --bucket skcr-files-prod \
     --prefix cf-logs/E2XLBJ13K3RVLX.2026-10-29-11 --query 'Contents[].Key' \
     --output text --profile $P | tr '\t' '\n' | grep -v None \
     | while read k; do aws s3 cp --quiet s3://skcr-files-prod/$k cf/ --profile $P; done
   ```

   Gotcha: `skcr-files` (no `-prod`) also has a `cf-logs/` prefix but it is **not**
   the prod distribution's target. Confirm with
   `aws cloudfront get-distribution-config --id E2XLBJ13K3RVLX --query DistributionConfig.Logging`.

3. **Join** on a ±1–2 s window around each CloudWatch timestamp. CloudFront TSV
   fields: `$1` date, `$2` time, `$5` c-ip, `$6` method, `$8` uri, `$9` status,
   `$10` referer, `$11` user agent, `$12` query string.

   ```bash
   zcat cf/*.gz | grep -v '^#' | awk -F'\t' \
     '$8 ~ /^\/api\/(competition|matches|physical|sessions)/ && $1=="2026-10-29" \
      && $2>="11:59:58" && $2<="12:00:01" {print $1,$2,$5,$6,$8,$9,$10,$11,substr($12,1,80)}'
   ```

   A match is solid when request count, endpoints and query params (e.g. the
   `match=` id lists, `component_permission_for=`) line up one-to-one. Other
   clients hit the same endpoints in the same second — never match on time alone.

## Reading the result

* **WAL (Web App Lab) traffic is not the end user.** The WAL (client web app;
  data-analysis team POC that went to prod, being replaced by Orion; lives in
  their own GitHub/GCP stack, not our GitLab — ask Adrien Diou-Hirtz /
  Edouard Vaché, #webapplab-support) logs users in
  server-side via `POST /api/sessions` and calls the API with their session from
  its own backend. Signature: referer exactly `https://skillcorner.com/api`, UA
  `python-requests/2.32.4`, IP from a rotating Google pool `34.34.246.x`
  (in `goog.json`, not `cloud.json`), many users per IP. Our logs only ever hold
  the WAL server IP for these; the browser IP, if anywhere, is on the WAL side.
  In CloudWatch, `referer = "https://skillcorner.com/api"` isolates WAL calls.
* UA `python-requests/x` / `fitrequest.skillcorner.x` (our SDK) / `httr` /
  `Java-http-client` = script; browsers show `Mozilla/5.0 … Chrome/…` and
  referer `https://skillcorner.com/api/docs/` or `/app/...`.
* IP ownership: check Google's published ranges (`gstatic.com/ipranges/goog.json`
  vs `cloud.json`). In `goog.json` but not `cloud.json` = Google-run serverless
  egress, not a customer's GCP VM — the IP rotates within the block per run.
* CloudFront logs are kept ~1 week: older sessions can only be described from
  CloudWatch (what was called), not traced to an IP.
