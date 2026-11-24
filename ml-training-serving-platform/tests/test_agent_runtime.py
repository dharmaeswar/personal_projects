"""Tests for the agentic layer: packaging, tool registry, agent runtime."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_platform.agent_runtime import (
    AgentRuntime,
    RetryableError,
    Tool,
    ToolRegistry,
    build_platform_tools,
    explain_model,
    load_package,
    model_from_package,
    package_model,
    write_package,
)
from ml_platform.data import FEATURES, generate_applications
from ml_platform.registry import Registry
from ml_platform.serving import ServingService
from ml_platform.training import evaluate, train


def _fresh(tmp_path):
    registry = Registry(str(tmp_path / "registry.json"))
    train_rows = generate_applications(400, seed=42)
    eval_rows = generate_applications(200, seed=99)
    return registry, train_rows, eval_rows


def test_package_round_trip_and_checksum(tmp_path):
    rows = generate_applications(400, seed=42)
    model = train(rows, epochs=50, seed=7)
    manifest = package_model(model, "credit-decision", "credit-decision-v1",
                             metrics=evaluate(model, rows))
    assert manifest["format"] == "ml-platform-package/1"
    assert [i["name"] for i in manifest["inputs"]] == [
        "income", "debt_ratio", "credit_history_years", "delinquencies", "amount"]
    assert manifest["sha256"]
    path = write_package(manifest, str(tmp_path / "pkg.json"))
    loaded = load_package(path)
    assert loaded["sha256"] == manifest["sha256"]
    restored = model_from_package(loaded)
    assert restored.predict_proba(rows[0][0]) == pytest.approx(
        model.predict_proba(rows[0][0]))


def test_package_tamper_detected(tmp_path):
    rows = generate_applications(200, seed=42)
    model = train(rows, epochs=20, seed=7)
    manifest = package_model(model, "credit-decision", "credit-decision-v1")
    path = write_package(manifest, str(tmp_path / "pkg.json"))
    data = json.load(open(path))
    data["weights"][0] += 1.0  # tamper after the checksum was computed
    json.dump(data, open(path, "w"))
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_package(path)


def test_package_wrong_format_rejected(tmp_path):
    path = tmp_path / "bad.json"
    json.dump({"format": "something-else/9", "weights": []}, open(path, "w"))
    with pytest.raises(ValueError, match="unsupported package format"):
        load_package(str(path))


def test_explain_model_ranks_and_sums_to_one():
    rows = generate_applications(400, seed=42)
    model = train(rows, epochs=50, seed=7)
    ranked = explain_model(model)
    assert len(ranked) == 5
    assert ranked[0]["importance"] >= ranked[-1]["importance"]
    assert sum(r["importance"] for r in ranked) == pytest.approx(1.0, abs=0.01)
    assert ranked[0]["feature"] in FEATURES  # top feature is data-dependent
    assert {r["feature"] for r in ranked} == set(FEATURES)


def test_tool_registry_rejects_unknown_tool_and_missing_inputs():
    tools = ToolRegistry()
    tools.register(Tool("echo", "Echo a value.", {"value": str}, lambda value: value))
    assert tools.call("nope")["ok"] is False
    assert tools.call("echo")["ok"] is False
    assert tools.call("echo", value="hi") == {"ok": True, "result": "hi"}
    assert len(tools.list_tools()) == 1
    assert tools.list_tools()[0]["name"] == "echo"


def test_guarded_tool_needs_approval(tmp_path):
    registry, train_rows, eval_rows = _fresh(tmp_path)
    tools = build_platform_tools(registry, train_rows, eval_rows)
    assert tools.call("promote_model")["ok"] is False  # no candidate + no approval
    tools.call("train_model", name="credit-decision", epochs=20, seed=7)
    assert tools.call("promote_model")["ok"] is False  # approval missing
    assert registry.production_version() is None
    assert tools.call("promote_model", approved=True)["ok"] is True
    assert registry.production_version() is not None


def test_agent_validate_and_promote_happy_path(tmp_path):
    registry, train_rows, eval_rows = _fresh(tmp_path)
    tools = build_platform_tools(registry, train_rows, eval_rows)
    agent = AgentRuntime(tools)
    result = agent.run("validate_and_promote",
                       task_args={"promote_model": {"approved": True},
                                  "package_model": {"out_dir": str(tmp_path)}})
    assert result["status"] == "completed", result
    assert [t["tool"] for t in result["trace"]] == [
        "train_model", "evaluate_candidate", "package_model", "promote_model"]
    assert all(t["status"] == "ok" for t in result["trace"])
    promoted = registry.production_version()
    assert promoted is not None
    assert os.path.exists(str(tmp_path / f"{promoted}.package.json"))
    assert load_package(str(tmp_path / f"{promoted}.package.json"))["model_version"] == promoted


def test_agent_promote_blocked_without_approval(tmp_path):
    registry, train_rows, eval_rows = _fresh(tmp_path)
    tools = build_platform_tools(registry, train_rows, eval_rows)
    agent = AgentRuntime(tools)
    result = agent.run("validate_and_promote",
                       task_args={"package_model": {"out_dir": str(tmp_path)}})
    assert result["status"] == "failed"
    assert registry.production_version() is None  # nothing promoted
    assert result["trace"][-1]["tool"] == "promote_model"


def test_agent_gate_failure_stops_before_promote(tmp_path):
    registry, train_rows, eval_rows = _fresh(tmp_path)
    tools = build_platform_tools(registry, train_rows, eval_rows)
    # Seed production with a strong model first.
    model = train(train_rows, epochs=300, seed=7)
    v1 = registry.register("credit-decision", model, evaluate(model, eval_rows))
    registry.promote(v1)
    agent = AgentRuntime(tools)
    # An impossible improvement bar forces the gate to fail.
    result = agent.run("validate_and_promote",
                       task_args={"evaluate_candidate": {"min_improvement": 0.9},
                                  "promote_model": {"approved": True},
                                  "package_model": {"out_dir": str(tmp_path)}})
    assert result["status"] == "gate_failed"
    assert registry.production_version() == v1  # production untouched
    skipped = [t for t in result["trace"] if t["status"] == "skipped"]
    assert {t["tool"] for t in skipped} == {"package_model", "promote_model"}


def test_agent_retries_transient_failure():
    tools = ToolRegistry()
    calls = {"n": 0}

    def flaky(value):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryableError("transient blip")
        return value * 2

    tools.register(Tool("flaky", "Fails once, then works.", {"value": int}, flaky))
    agent = AgentRuntime(tools)
    # Run the flaky tool through the runtime's retry path directly.
    record = {"attempts": 0}
    result = agent._call_with_retries("flaky", {"value": 21}, record)
    assert result == {"ok": True, "result": 42}
    assert record["attempts"] == 2


def test_agent_unknown_task():
    agent = AgentRuntime(ToolRegistry())
    result = agent.run("do_everything")
    assert result["status"] == "failed"
    assert "unknown task" in result["error"]


def test_drift_response_task_no_drift(tmp_path):
    registry, train_rows, eval_rows = _fresh(tmp_path)
    model = train(train_rows, epochs=50, seed=7)
    v1 = registry.register("credit-decision", model, evaluate(model, eval_rows))
    registry.promote(v1)
    serving = ServingService(registry, train_rows)
    tools = build_platform_tools(registry, train_rows, eval_rows, serving=serving)
    agent = AgentRuntime(tools)
    result = agent.run("drift_response")
    assert result["status"] == "completed"
    assert result["trace"][0]["result"]["recommendation"] == "no action"
