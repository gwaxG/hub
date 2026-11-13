import io
import json
import subprocess
from pathlib import Path

import httpx
import pytest

import qa_run
from qa_run import (
    MISSING,
    DeploymentChecker,
    Evidence,
    Expect,
    ExpectationVerifier,
    HttpExecutor,
    LambdaExecutor,
    Matcher,
    PipelineExecutor,
    Plan,
    QaRunner,
    resolve_path,
)


def completed(
    stdout: str = "", returncode: int = 0, stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def make_plan(**overrides) -> Plan:
    data = {
        "name": "p",
        "env": "andrei",
        "steps": [{"id": "a", "kind": "http", "request": {"path": "/x"}}],
    }
    return Plan.model_validate({**data, **overrides})


@pytest.mark.parametrize(
    ("path", "expected"),
    [("a.b", 1), ("a.list.1.c", 3), ("a.missing", MISSING), ("a.list.9", MISSING)],
)
def test_resolve_path(path, expected):
    data = {"a": {"b": 1, "list": [{"c": 2}, {"c": 3}]}}
    assert resolve_path(data, path) == expected or resolve_path(data, path) is expected


@pytest.mark.parametrize(
    ("spec", "value", "ok"),
    [
        ("exists", 0, True),
        ("exists", MISSING, False),
        ("absent", MISSING, True),
        ("non_empty", [], False),
        ("non_empty", [1], True),
        ({"gte": 5}, 7, True),
        ({"gte": 5}, MISSING, False),
        ({"contains": "x"}, "xyz", True),
        ({"ne": 1}, 2, True),
        ({"some": "object"}, {"some": "object"}, True),
        (42, 42, True),
    ],
)
def test_matcher(spec, value, ok):
    assert Matcher(spec).matches(value) is ok


def test_verifier_reports_each_check():
    expect = Expect(status=200, json_paths={"data.0.id": "exists"})
    checks = ExpectationVerifier().verify(
        expect, Evidence(status=500, body={"data": []})
    )
    assert {c.name: c.passed for c in checks} == {
        "no_error": True,
        "status": False,
        "json:data.0.id": False,
    }


def test_needs_approval():
    assert not make_plan().needs_approval
    assert make_plan(env="dev").needs_approval
    pipeline = {"id": "p", "kind": "pipeline", "match_id": 1}
    assert make_plan(steps=[pipeline]).needs_approval


def test_http_executor_decodes_json():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"path": request.url.path})
    )
    client = httpx.Client(base_url="https://api.test", transport=transport)
    step = make_plan().steps[0]
    evidence = HttpExecutor(client).execute(step)
    assert (evidence.status, evidence.body) == (200, {"path": "/x"})


class FakeLambda:
    def __init__(self, response):
        self.response = response

    def invoke(self, **_):
        return self.response


def test_lambda_executor_flags_function_error():
    response = {
        "StatusCode": 200,
        "FunctionError": "Unhandled",
        "Payload": io.BytesIO(b'{"errorMessage": "boom"}'),
    }
    step = make_plan(steps=[{"id": "l", "kind": "lambda", "function": "f"}]).steps[0]
    evidence = LambdaExecutor(
        lambda _region: FakeLambda(response), "eu-central-1"
    ).execute(step)
    assert evidence.error == "FunctionError: Unhandled"
    assert evidence.body == {"errorMessage": "boom"}


class ScriptedRunner:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        return self.outputs.pop(0)


def test_pipeline_polls_until_terminal():
    running = json.dumps([{"pipeline_status": "RUNNING", "processed_at": "1"}])
    done = json.dumps([{"pipeline_status": "SUCCEEDED", "processed_at": "2"}])
    runner = ScriptedRunner([completed(), completed(running), completed(done)])
    step = make_plan(
        steps=[
            {"id": "p", "kind": "pipeline", "match_id": 7, "args": ["--start-at", "x"]}
        ]
    ).steps[0]
    evidence = PipelineExecutor(
        "andrei", "plan", runner, sleep=lambda _s: None
    ).execute(step)
    assert evidence.sfn_status == "SUCCEEDED"
    assert runner.calls[0][:7] == [
        "francli",
        "football",
        "run",
        "--env",
        "andrei",
        "--match-id",
        "7",
    ]
    assert runner.calls[0][-2:] == ["--start-at", "x"]


def test_pipeline_launch_failure_is_error():
    runner = ScriptedRunner([completed(returncode=1, stderr="bad env")])
    step = make_plan(steps=[{"id": "p", "kind": "pipeline", "match_id": 7}]).steps[0]
    evidence = PipelineExecutor(
        "andrei", "plan", runner, sleep=lambda _s: None
    ).execute(step)
    assert "bad env" in evidence.error


@pytest.mark.parametrize(("tag_sha", "ok"), [("abc", True), ("old", False)])
def test_deployment_checker(tag_sha, ok):
    out = f"abc\trefs/heads/feat/x\n{tag_sha}\trefs/tags/andrei\n"
    plan = make_plan(deployments=[{"repo_path": "/r/wilson", "branch": "feat/x"}])
    problems = DeploymentChecker(ScriptedRunner([completed(out)])).problems(plan)
    assert (problems == []) is ok


class StubExecutor:
    def __init__(self, evidence):
        self.evidence = evidence

    def execute(self, _step):
        if isinstance(self.evidence, Exception):
            raise self.evidence
        return self.evidence


def test_runner_skips_dependents_of_failed_step():
    steps = [
        {
            "id": "pipe",
            "kind": "pipeline",
            "match_id": 1,
            "expect": {"sfn_status": "SUCCEEDED"},
        },
        {
            "id": "query",
            "kind": "http",
            "request": {"path": "/m"},
            "requires": ["pipe"],
        },
    ]
    executors = {
        "pipeline": StubExecutor(Evidence(sfn_status="FAILED")),
        "http": StubExecutor(Evidence(status=200)),
    }
    results = QaRunner(executors, ExpectationVerifier()).run(
        make_plan(steps=steps).steps
    )
    assert [(r.step_id, r.passed) for r in results] == [
        ("pipe", False),
        ("query", False),
    ]
    assert results[1].checks[0].name == "requires"


def test_runner_turns_adapter_exception_into_failed_step():
    executors = {"http": StubExecutor(RuntimeError("timeout"))}
    [result] = QaRunner(executors, ExpectationVerifier()).run(make_plan().steps)
    assert not result.passed
    assert result.evidence["error"] == "RuntimeError: timeout"


def test_main_refuses_unapproved_shared_env(tmp_path: Path):
    plan_file = tmp_path / "plan.yaml"
    plan_file.write_text("name: p\nenv: dev\nsteps: []\n")
    assert qa_run.main([str(plan_file)]) == 2


def test_deployment_checker_uses_per_deployment_env():
    out = "abc\trefs/heads/feat/x\nabc\trefs/tags/dev\n"
    plan = make_plan(
        env="mr_1",
        deployments=[{"repo_path": "/r/wilson", "branch": "feat/x", "env": "dev"}],
    )
    runner = ScriptedRunner([completed(out)])
    assert DeploymentChecker(runner).problems(plan) == []
    assert runner.calls[0][-1] == "refs/tags/dev"
    assert plan.needs_approval
