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
CRONJOBS = {"ingest-players", "refresh-images"}
POLL_SECONDS = 15


def kubectl(*args: str, capture: bool = True, stdin: str | None = None) -> str:
    """Run kubectl in the dev namespace; raise on a non-zero exit."""
    cmd = ["kubectl", "-n", NAMESPACE, *args]
    result = subprocess.run(
        cmd, check=True, capture_output=capture, text=True, input=stdin
    )
    return (result.stdout or "").strip()


def with_limit(command: list[str], limit: int) -> list[str]:
    """Return the container command with its `--limit` value replaced (or added)."""
    if "--limit" not in command:
        return [*command, "--limit", str(limit)]
    index = command.index("--limit") + 1
    return [*command[:index], str(limit), *command[index + 1 :]]


def trigger(cronjob: str, limit: int | None) -> str:
    """Create a Job from the CronJob template (optionally with a new limit); return its name."""
    job = f"{cronjob}-manual-{int(time.time())}"
    source = f"--from=cronjob/football-metadata-service-dev-{cronjob}"
    manifest = json.loads(
        kubectl("create", "job", source, job, "--dry-run=client", "-o", "json")
    )
    if limit is not None:
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        container["command"] = with_limit(container["command"], limit)
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
        "--limit", type=int, help="override the CronJob's --limit (per entity type)"
    )
    parser.add_argument(
        "--timeout", type=int, default=90, help="minutes to wait (default 90)"
    )
    args = parser.parse_args()
    os.environ.setdefault("AWS_PROFILE", "Production.Skcr-Software-Common-Role")

    job = trigger(args.cronjob, args.limit)
    ok = wait(job, args.timeout)
    kubectl("logs", f"job/{job}", capture=False)
    print(f"job/{job}: {'succeeded' if ok else 'FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
