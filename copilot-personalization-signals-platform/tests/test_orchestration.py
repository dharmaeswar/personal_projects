import pytest

from signals.orchestration import Orchestrator, Task, TransientError


def _tasks(calls):
    def make(name, deps=()):
        def fn(ctx):
            calls.append(name)
            return name
        return Task(name, fn, depends_on=deps)
    return [make("ingest"), make("validate", ("ingest",)),
            make("batch", ("validate",)), make("publish", ("batch",))]


def test_tasks_run_in_dependency_order():
    calls = []
    Orchestrator().run("r1", _tasks(calls), {"inputs": {}})
    assert calls == ["ingest", "validate", "batch", "publish"]


def test_resume_skips_succeeded_tasks():
    orch = Orchestrator()
    calls = []
    orch.run("r1", _tasks(calls), {"inputs": {}})
    results = orch.run("r1", _tasks(calls), {"inputs": {}})
    assert calls == ["ingest", "validate", "batch", "publish"]  # no re-run
    assert all(v == "skipped (already succeeded)" for v in results.values())


def test_transient_failure_retried_once():
    attempts = {"n": 0}

    def flaky(ctx):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise TransientError("flaky read")
        return "ok"

    results = Orchestrator().run("r2", [Task("ingest", flaky)], {"inputs": {}})
    assert results["ingest"] == "ok" and attempts["n"] == 2


def test_transient_failure_twice_raises():
    def always_flaky(ctx):
        raise TransientError("always down")

    with pytest.raises(TransientError):
        Orchestrator().run("r3", [Task("ingest", always_flaky)], {"inputs": {}})


def test_cycle_detected():
    tasks = [Task("a", lambda ctx: None, depends_on=("b",)),
             Task("b", lambda ctx: None, depends_on=("a",))]
    with pytest.raises(ValueError, match="cycle"):
        Orchestrator().run("r4", tasks, {"inputs": {}})


def test_unknown_dependency_detected():
    tasks = [Task("a", lambda ctx: None, depends_on=("nope",))]
    with pytest.raises(ValueError, match="unknown dependency"):
        Orchestrator().run("r5", tasks, {"inputs": {}})
