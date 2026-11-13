# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "pyyaml>=6", "boto3>=1.34", "pydantic>=2.7"]
# ///
"""Deterministic executor for QA plans written by the qa-planner agent."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, ClassVar, Literal, Protocol

import httpx
import yaml
from pydantic import BaseModel, Field

SHARED_ENVS = frozenset({"dev", "staging", "prod"})
RUNNING_SFN_STATUSES = frozenset({"RUNNING", "PENDING_REDRIVE"})
MAX_BODY_CHARS = 20_000
MISSING = object()


# ---------------------------------------------------------------- plan schema


class Expect(BaseModel):
    status: int | None = None
    json_paths: dict[str, Any] = Field(default_factory=dict)
    no_error: bool = True
    sfn_status: str | None = None


class HttpRequest(BaseModel):
    method: str = "GET"
    path: str
    params: dict[str, Any] = Field(default_factory=dict)
    body: Any = None


class StepBase(BaseModel):
    id: str
    description: str = ""
    mutates: bool = False
    requires: list[str] = Field(default_factory=list)
    expect: Expect = Field(default_factory=Expect)


class HttpStep(StepBase):
    kind: Literal["http"]
    request: HttpRequest


class LambdaStep(StepBase):
    kind: Literal["lambda"]
    function: str
    payload: dict[str, Any] = Field(default_factory=dict)
    region: str | None = None


class PipelineStep(StepBase):
    kind: Literal["pipeline"]
    match_id: int
    args: list[str] = Field(default_factory=list)
    timeout_min: int = 180


Step = Annotated[HttpStep | LambdaStep | PipelineStep, Field(discriminator="kind")]


class Deployment(BaseModel):
    repo_path: Path
    branch: str
    env: str | None = (
        None  # defaults to plan.env (e.g. wilson on dev while football runs on mr_<iid>)
    )


class Plan(BaseModel):
    name: str
    env: str
    api_base_url: str | None = None
    aws_region: str = "eu-central-1"
    deployments: list[Deployment] = Field(default_factory=list)
    steps: list[Step]

    @property
    def needs_approval(self) -> bool:
        risky_step = any(step.mutates or step.kind == "pipeline" for step in self.steps)
        shared = {self.env, *(dep.env for dep in self.deployments)} & SHARED_ENVS
        return bool(shared) or risky_step


# ---------------------------------------------------------------- results


@dataclass
class Evidence:
    status: int | None = None
    body: Any = None
    error: str | None = None
    sfn_status: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class StepResult:
    step_id: str
    kind: str
    passed: bool
    checks: list[Check]
    evidence: dict[str, Any]
    duration_s: float


# ---------------------------------------------------------------- assertions


def resolve_path(data: Any, path: str) -> Any:
    """Resolve a dotted path (``a.b.0.c``) inside decoded JSON; MISSING when absent."""
    current = data
    for part in path.split("."):
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return MISSING
    return current


class Matcher:
    """Evaluates one plan matcher: a keyword, an ``{op: value}`` dict, or a literal (equality)."""

    KEYWORDS: ClassVar[dict[str, Callable[[Any], bool]]] = {
        "exists": lambda v: v is not MISSING,
        "absent": lambda v: v is MISSING,
        "non_empty": lambda v: v is not MISSING and bool(v),
    }
    OPERATORS: ClassVar[dict[str, Callable[[Any, Any], bool]]] = {
        "eq": lambda v, e: v == e,
        "ne": lambda v, e: v != e,
        "gte": lambda v, e: v is not MISSING and v >= e,
        "lte": lambda v, e: v is not MISSING and v <= e,
        "contains": lambda v, e: v is not MISSING and e in v,
    }

    def __init__(self, spec: Any) -> None:
        self.spec = spec

    def matches(self, value: Any) -> bool:
        if isinstance(self.spec, str) and self.spec in self.KEYWORDS:
            return self.KEYWORDS[self.spec](value)
        if (
            isinstance(self.spec, dict)
            and len(self.spec) == 1
            and next(iter(self.spec)) in self.OPERATORS
        ):
            op, expected = next(iter(self.spec.items()))
            return self.OPERATORS[op](value, expected)
        return value == self.spec


class ExpectationVerifier:
    """Turns an Expect block plus collected Evidence into named checks."""

    def verify(self, expect: Expect, evidence: Evidence) -> list[Check]:
        checks = [self._error_check(evidence)] if expect.no_error else []
        if expect.status is not None:
            checks.append(
                Check(
                    "status", evidence.status == expect.status, f"got {evidence.status}"
                )
            )
        if expect.sfn_status is not None:
            checks.append(
                Check(
                    "sfn_status",
                    evidence.sfn_status == expect.sfn_status,
                    f"got {evidence.sfn_status}",
                )
            )
        checks.extend(
            self._path_check(path, spec, evidence.body)
            for path, spec in expect.json_paths.items()
        )
        return checks

    @staticmethod
    def _error_check(evidence: Evidence) -> Check:
        return Check("no_error", evidence.error is None, evidence.error or "ok")

    @staticmethod
    def _path_check(path: str, spec: Any, body: Any) -> Check:
        value = resolve_path(body, path)
        shown = (
            "<missing>" if value is MISSING else json.dumps(value, default=str)[:200]
        )
        return Check(f"json:{path}", Matcher(spec).matches(value), f"got {shown}")


# ---------------------------------------------------------------- executors


class CommandRunner(Protocol):
    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]: ...


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def decode_body(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return text[:MAX_BODY_CHARS]


class HttpExecutor:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def execute(self, step: HttpStep) -> Evidence:
        req = step.request
        response = self.client.request(
            req.method, req.path, params=req.params, json=req.body
        )
        return Evidence(
            status=response.status_code,
            body=decode_body(response.text),
            extra={"url": str(response.url)},
        )


class LambdaExecutor:
    def __init__(
        self, client_factory: Callable[[str], Any], default_region: str
    ) -> None:
        self.client_factory = client_factory
        self.default_region = default_region

    def execute(self, step: LambdaStep) -> Evidence:
        client = self.client_factory(step.region or self.default_region)
        response = client.invoke(
            FunctionName=step.function, Payload=json.dumps(step.payload).encode()
        )
        body = decode_body(response["Payload"].read().decode())
        error = response.get("FunctionError")
        return Evidence(
            status=response.get("StatusCode"),
            body=body,
            error=f"FunctionError: {error}" if error else None,
        )


class PipelineExecutor:
    """Launches the football pipeline with francli and polls its status until it reaches a terminal state."""

    def __init__(
        self,
        env: str,
        plan_name: str,
        runner: CommandRunner,
        sleep: Callable[[float], None],
        poll_s: int = 60,
    ):
        self.env = env
        self.plan_name = plan_name
        self.runner = runner
        self.sleep = sleep
        self.poll_s = poll_s

    def execute(self, step: PipelineStep) -> Evidence:
        launched_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        launch = self.runner(self._run_args(step))
        if launch.returncode != 0:
            return Evidence(error=f"francli run failed: {launch.stderr[-2000:]}")
        return self._wait(step, launched_at)

    def _run_args(self, step: PipelineStep) -> list[str]:
        base = [
            "francli",
            "football",
            "run",
            "--env",
            self.env,
            "--match-id",
            str(step.match_id),
        ]
        tags = [
            "--no-interactive",
            "--context-tag",
            "dev_and_test",
            "--context-detail",
            f"qa: {self.plan_name}",
        ]
        return [*base, *tags, *step.args]

    def _wait(self, step: PipelineStep, launched_at: str) -> Evidence:
        deadline = time.monotonic() + step.timeout_min * 60
        while time.monotonic() < deadline:
            run = self._latest_run(step.match_id, launched_at)
            if run and run.get("pipeline_status") not in RUNNING_SFN_STATUSES:
                return Evidence(sfn_status=run.get("pipeline_status"), body=run)
            self.sleep(self.poll_s)
        return Evidence(error=f"pipeline not terminal after {step.timeout_min} min")

    def _latest_run(self, match_id: int, since: str) -> dict[str, Any] | None:
        args = [
            "francli",
            "football",
            "status",
            "--env",
            self.env,
            "--match-id",
            str(match_id),
        ]
        result = self.runner(
            [*args, "--start", since, "--all-runs", "--format", "json"]
        )
        runs = decode_body(result.stdout) if result.returncode == 0 else []
        runs = runs if isinstance(runs, list) else []
        return max(runs, key=lambda r: r.get("processed_at", ""), default=None)


# ---------------------------------------------------------------- deployment guard


class DeploymentChecker:
    """Refuses to test stale code: the pirlo env tag must point at the branch head."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def problems(self, plan: Plan) -> list[str]:
        return [
            msg
            for dep in plan.deployments
            if (msg := self._check(dep, dep.env or plan.env))
        ]

    def _check(self, dep: Deployment, env: str) -> str | None:
        refs = self._remote_refs(dep, [f"refs/heads/{dep.branch}", f"refs/tags/{env}"])
        head, tag = refs.get(f"refs/heads/{dep.branch}"), refs.get(f"refs/tags/{env}")
        if head and head == tag:
            return None
        return f"{dep.repo_path.name}: env tag {env}={tag} does not match {dep.branch}={head}"

    def _remote_refs(self, dep: Deployment, refs: list[str]) -> dict[str, str]:
        result = self.runner(
            ["git", "-C", str(dep.repo_path), "ls-remote", "origin", *refs]
        )
        pairs = (
            line.split("\t") for line in result.stdout.splitlines() if "\t" in line
        )
        return {ref: sha for sha, ref in pairs}


# ---------------------------------------------------------------- orchestration


class QaRunner:
    def __init__(
        self, executors: dict[str, Any], verifier: ExpectationVerifier
    ) -> None:
        self.executors = executors
        self.verifier = verifier

    def run(self, steps: list[Step]) -> list[StepResult]:
        results: dict[str, StepResult] = {}
        for step in steps:
            failed = [
                dep
                for dep in step.requires
                if dep not in results or not results[dep].passed
            ]
            results[step.id] = (
                self._skip(step, failed) if failed else self._run_step(step)
            )
        return list(results.values())

    @staticmethod
    def _skip(step: Step, failed: list[str]) -> StepResult:
        print(f"  SKIP {step.id}: requires {failed}", flush=True)
        check = Check("requires", False, f"skipped, failed or missing: {failed}")
        return StepResult(step.id, step.kind, False, [check], {}, 0.0)

    def _run_step(self, step: Step) -> StepResult:
        print(f"▶ {step.id} ({step.kind}) {step.description}", flush=True)
        started = time.monotonic()
        evidence = self._collect(step)
        checks = self.verifier.verify(step.expect, evidence)
        passed = all(check.passed for check in checks)
        print(f"  {'PASS' if passed else 'FAIL'} {step.id}", flush=True)
        return StepResult(
            step.id,
            step.kind,
            passed,
            checks,
            asdict(evidence),
            round(time.monotonic() - started, 1),
        )

    def _collect(self, step: Step) -> Evidence:
        try:
            return self.executors[step.kind].execute(step)
        except Exception as error:  # noqa: BLE001 - any adapter failure is a failed step, not a crash
            return Evidence(error=f"{type(error).__name__}: {error}")


def build_http_client(plan: Plan) -> httpx.Client:
    user, password = os.environ.get("QA_API_USER"), os.environ.get("QA_API_PASSWORD")
    auth = httpx.BasicAuth(user, password) if user and password else None
    return httpx.Client(base_url=plan.api_base_url or "", auth=auth, timeout=60)


def build_runner(plan: Plan) -> QaRunner:
    import boto3

    executors = {
        "http": HttpExecutor(build_http_client(plan)),
        "lambda": LambdaExecutor(
            lambda region: boto3.client("lambda", region_name=region), plan.aws_region
        ),
        "pipeline": PipelineExecutor(plan.env, plan.name, run_command, time.sleep),
    }
    return QaRunner(executors, ExpectationVerifier())


def load_plan(path: Path, only: set[str] | None) -> Plan:
    plan = Plan.model_validate(yaml.safe_load(path.read_text()))
    if only:
        plan.steps = [step for step in plan.steps if step.id in only]
    return plan


def write_report(out: Path, plan: Plan, results: list[StepResult]) -> None:
    report = {
        "plan": plan.name,
        "env": plan.env,
        "finished_at": datetime.now(UTC).isoformat(),
        "passed": all(r.passed for r in results),
        "results": [asdict(r) for r in results],
    }
    out.write_text(json.dumps(report, indent=2, default=str))
    print(f"{sum(r.passed for r in results)}/{len(results)} steps passed → {out}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--out", type=Path, default=Path("qa-results.json"))
    parser.add_argument(
        "--approved",
        action="store_true",
        help="user approved shared-env / pipeline / mutating steps",
    )
    parser.add_argument("--only", help="comma-separated step ids to run")
    parser.add_argument("--skip-deploy-check", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    plan = load_plan(args.plan, set(args.only.split(",")) if args.only else None)
    if plan.needs_approval and not args.approved:
        print(
            "REFUSED: plan targets a shared env or has pipeline/mutating steps; rerun with --approved",
            file=sys.stderr,
        )
        return 2
    if not args.skip_deploy_check and (
        problems := DeploymentChecker(run_command).problems(plan)
    ):
        print("REFUSED: stale deployment\n  " + "\n  ".join(problems), file=sys.stderr)
        return 2
    results = build_runner(plan).run(plan.steps)
    write_report(args.out, plan, results)
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
