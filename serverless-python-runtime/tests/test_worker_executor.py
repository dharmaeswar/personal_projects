import pytest

from runtime.executor import Executor
from runtime.config import RuntimeConfig
from runtime.worker import Worker, WorkerTimeout


@pytest.fixture()
def handler(tmp_path):
    path = tmp_path / "handler.py"
    path.write_text(
        "import time\n"
        "\n"
        "def handle(event):\n"
        "    return {'echo': event.get('n', 0)}\n"
        "\n"
        "def slow(event):\n"
        "    time.sleep(5)\n"
        "    return {}\n"
        "\n"
        "def boom(event):\n"
        "    raise ValueError('boom on purpose')\n"
    )
    return str(path)


def test_first_invoke_is_cold_then_warm(handler):
    with Worker() as worker:
        first = worker.invoke(handler, "handle", {"n": 1})
        second = worker.invoke(handler, "handle", {"n": 2})
    assert first["ok"] is True and first["cold"] is True
    assert first["result"] == {"echo": 1}
    assert first["import_ms"] >= 0
    assert second["ok"] is True and second["cold"] is False
    assert second["import_ms"] == 0.0
    assert second["result"] == {"echo": 2}
    assert worker.invocations == 2


def test_handler_error_is_reported_not_raised(handler):
    with Worker() as worker:
        response = worker.invoke(handler, "boom", {})
    assert response["ok"] is False
    assert "ValueError: boom on purpose" in response["error"]


def test_worker_timeout_kills_stuck_handler(handler):
    with Worker() as worker:
        with pytest.raises(WorkerTimeout):
            worker.invoke(handler, "slow", {}, timeout_s=1)
        assert worker.alive is False


def test_executor_reuses_warm_worker_and_records_metrics(handler):
    with Executor(RuntimeConfig(max_concurrency=2)) as executor:
        cold = executor.invoke(handler, "handle", {"n": 1})
        warm = executor.invoke(handler, "handle", {"n": 2})
        failed = executor.invoke(handler, "boom", {})
    assert cold["cold"] is True
    assert warm["cold"] is False
    assert failed["ok"] is False
    summary = executor.metrics.summary()
    assert summary["invocations"] == 3
    # "boom" runs in its own worker (keyed by function), so its first call
    # is a cold start too: 2 cold (handle, boom), 1 warm (second handle).
    assert summary["cold_starts"] == 2
    assert summary["warm_invocations"] == 1
    assert summary["failures"] == 1
    assert summary["p50_ms"] > 0


def test_executor_enforces_concurrency_limit(handler, tmp_path):
    other = tmp_path / "other.py"
    other.write_text("def handle(event):\n    return {}\n")
    with Executor(RuntimeConfig(max_concurrency=1)) as executor:
        executor.invoke(handler, "handle", {})
        with pytest.raises(RuntimeError, match="concurrency limit"):
            executor.invoke(str(other), "handle", {})
