"""Tests: observability (logs, traces, metrics, diagnostics) and SDK/CLI."""

import json
import subprocess
import sys

import pytest

from integration_surface.context import CallerContext
from integration_surface.observability import Metrics, Observer
from integration_surface.sdk import IntegrationClient


def _client():
    ctx = CallerContext(user_id="u1", tenant_id="tenant-demo",
                        scopes=frozenset({"amp:read", "amp:migrate"}))
    return IntegrationClient(ctx)


def test_metrics_summary_percentiles():
    m = Metrics()
    for ms in [10, 20, 30, 40, 50]:
        m.observe("amp.analyze_schema", ms, "ok")
    m.observe("amp.analyze_schema", 99, "error")
    s = m.summary("amp.analyze_schema")
    assert s["calls"] == 6
    assert s["errors"] == 1
    assert s["p50_ms"] == 40
    assert s["max_ms"] == 99


def test_observer_records_trace_log_and_metrics():
    obs = Observer()
    trace = obs.start_trace("amp.analyze_schema")
    obs.finish(trace, "ok", tenant="tenant-demo")
    assert len(obs.traces) == 1
    assert obs.traces[0].latency_ms >= 0
    assert obs.metrics.summary("amp.analyze_schema")["calls"] == 1
    assert obs.logs[-1]["status"] == "ok"
    assert obs.logs[-1]["tenant"] == "tenant-demo"


def test_diagnostics_lists_recent_failures():
    client = _client()
    client.analyze_schema("orders")
    client.registry.invoke("amp.analyze_schema", {}, client.ctx)  # malformed
    diag = client.registry.observer.diagnostics("amp.analyze_schema")
    assert diag["metrics"]["calls"] == 2
    assert diag["metrics"]["errors"] == 1
    assert diag["recent_failures"][0]["error"] == "contract_violation"


def test_sdk_end_to_end_flow():
    client = _client()
    assert len(client.list_tools()) == 7
    analysis = client.analyze_schema("billing")
    assert analysis.ok is True
    mapped = client.transform_table("billing", "invoices", version="2.0")
    assert mapped.ok is True
    dry = client.dry_run_migration("orders")
    assert dry.partial is True  # deterministic mixed outcome
    validated = client.validate_migrated(500, 500)
    assert validated.ok is True
    suggestion = client.suggest_mapping("map invoices", seed=1)
    assert suggestion.ok is True
    assert suggestion.data["attempts"] == 1


def test_cli_list_tools_and_analyze():
    out = subprocess.run(
        [sys.executable, "-m", "integration_surface.cli", "list-tools"],
        capture_output=True, text=True, cwd=".",
    )
    assert out.returncode == 0
    tools = json.loads(out.stdout)
    assert any(t["name"] == "amp.analyze_schema" for t in tools)
    out = subprocess.run(
        [sys.executable, "-m", "integration_surface.cli", "analyze", "orders"],
        capture_output=True, text=True, cwd=".",
    )
    assert out.returncode == 0
    assert json.loads(out.stdout)["ok"] is True


def test_cli_failed_call_exits_nonzero():
    out = subprocess.run(
        [sys.executable, "-m", "integration_surface.cli", "validate", "10", "9"],
        capture_output=True, text=True, cwd=".",
    )
    assert out.returncode == 1
    assert json.loads(out.stdout)["ok"] is False
