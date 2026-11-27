# /// script
# requires-python = ">=3.11"
# ///
"""Trigger a suspended football-metadata-service dev CronJob by hand and wait for it."""

import argparse
import json
import os
import subprocess
import sys
import time

NAMESPACE = "football-metadata-service-dev"
CRONJOBS = {
    "ingest-metadata",
    "refresh-images",
    "ingest-players",
}  # ingest-players: old name, until argocd !30 merges
POLL_SECONDS = 15


def kubectl(*args: str, capture: bool = True, stdin: str | None = None) -> str:
    """Run kubectl in the dev namespace; raise on a non-zero exit."""
    cmd = ["kubectl", "-n", NAMESPACE, *args]
    result = subprocess.run(
        cmd, check=True, capture_output=capture, text=True, input=stdin
    )
    return (result.stdout or "").strip()


def with_args(command: list[str], job_args: list[str]) -> list[str]:
    """Return the container command (`python -m <module> ...`) with its arguments replaced."""
    return [*command[:3], *job_args]


def trigger(cronjob: str, job_args: list[str]) -> str:
    """Create a Job from the CronJob template (optionally with other arguments); return its name."""
    job = f"{cronjob}-manual-{int(time.time())}"
    source = f"--from=cronjob/football-metadata-service-dev-{cronjob}"
    manifest = json.loads(
        kubectl("create", "job", source, job, "--dry-run=client", "-o", "json")
    )
    if job_args:
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        container["command"] = with_args(container["command"], job_args)
    kubectl("create", "-f", "-", stdin=json.dumps(manifest))
    print(f"created job/{job}")
    return job


def wait(job: str, timeout_minutes: int) -> bool:
    """Poll the Job until it succeeds or fails; return True on success."""
    deadline = time.monotonic() + timeout_minutes * 60
    while time.monotonic() < deadline:
        status = kubectl(
            "get", f"job/{job}", "-o", "jsonpath={.status.succeeded}/{.status.failed}"
        )
        if status.startswith("1"):
            return True
        if status.endswith("1"):
            return False
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"job/{job} still running after {timeout_minutes} min")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cronjob", choices=sorted(CRONJOBS))
    parser.add_argument(
        "--timeout", type=int, default=90, help="minutes to wait (default 90)"
    )
    parser.add_argument(
        "job_args",
        nargs="*",
        help="after `--`: replace the CronJob's arguments, e.g. `-- --limit 100`"
        " or `-- --type team_logo --competition 37`",
    )
    args = parser.parse_args()
    os.environ.setdefault("AWS_PROFILE", "Production.Skcr-Software-Common-Role")

    job = trigger(args.cronjob, args.job_args)
    ok = wait(job, args.timeout)
    kubectl("logs", f"job/{job}", capture=False)
    print(f"job/{job}: {'succeeded' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
