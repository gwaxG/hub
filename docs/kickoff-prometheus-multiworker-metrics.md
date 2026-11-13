---
repo: [kickoff, gaffer, orion, mercato, supporter, skcr-registry-portal, match-lifecycle, basketball-metadata-service]
mr: [kickoff!125]
verified_at: 2026-11-12
---

# kickoff services: /metrics wrong with several uvicorn workers

- **Symptom.** On services scaffolded from kickoff, `http_request_duration_seconds_count` goes up and down on one pod between scrapes. Grafana `rate()` reads each drop as a counter reset: gaffer-prod showed about 1,000 `/health` req/s when the real rate is about 0.1. Every `histogram_quantile()` is noise.
- **Root cause.** The image runs `uvicorn --workers ${UVICORN_WORKERS:-4}`. Each worker has its own `prometheus_client` registry, and a scrape reads only the worker that accepts it.
- **Clean services.** These either run one worker (football-metadata-service !16, skcr-aft `UVICORN_WORKERS=1`) or use multiprocess mode (basketball-metadata-service, commit `1efddd8`).
- **Fix (kickoff!125, template 2.3.1):**
  - Dockerfile: `ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc`. The directory is created and chowned before `USER appuser`, and the `CMD` runs `rm -f "$DIR"/*.db` before `exec uvicorn`. The variable is read at import time, so the image must set it, not the app.
  - `/metrics` builds a new `CollectorRegistry()` + `MultiProcessCollector` per scrape when the variable is set, otherwise uses the default `REGISTRY`.
  - The dashboard adds `path!="/api/health"`: on a quiet service, probes are 75 to 99 % of requests and drag the percentiles down.
- **Rules in multiprocess mode:**
  - A `Gauge` needs `multiprocess_mode` set to `sum`, `max`, `min` or `mostrecent`. `live*` modes never drop dead workers, because uvicorn has no `mark_process_dead` hook.
  - `process_*` / `python_*` series disappear; use cAdvisor instead.
  - Dead workers' files stay, so worker recycling (orion `UVICORN_LIMIT_MAX_REQUESTS`) grows the directory slowly.
- **Rollout.** `kickoff update` is add-only, and `app/**` and the dashboard are in `DRIFT_EXCLUDE`, so each existing service needs a hand MR (Dockerfile, `/metrics`, dashboard). gaffer and orion hardcode `--workers 4` in `CMD` and probe `/health`, not `/api/health`.
