"""Tests for audit trails and reproducible run artifacts."""

import json
import os

from agent_eval.agent import AnalyticsAgent
from agent_eval.provenance import render_report, run_record, write_artifact
from agent_eval.sandbox import Sandbox
from agent_eval.tools import ToolServer


def test_run_record_captures_sql_hash_and_provenance(tmp_path):
    agent = AnalyticsAgent(ToolServer(Sandbox()))
    result = agent.answer("What is the total score of all posts in python?")
    record = run_record(result.question, result, "community-analytics-v1")
    assert record["status"] == "complete"
    assert record["sql_hash"] and len(record["sql_hash"]) == 12
    assert record["provenance"]["dataset_version"] == "community-analytics-v1"
    assert len(record["tool_calls"]) == 5
    path = tmp_path / "record.json"
    write_artifact(record, str(path))
    assert json.loads(path.read_text())["run_id"] == record["run_id"]


def test_render_report_lists_gate_and_cases():
    results = {
        "task_set_version": "v1",
        "pass_count": 7, "total": 8, "pass_rate": 0.875,
        "failure_handling": {"id": "unknown-community", "passed": True,
                             "failure_reason": "could not translate"},
        "failure_modes": {"wrong-result": 1},
        "cases": [{"id": "a", "category": "ranking", "human_reviewed": True,
                   "passed": True, "grounded": True, "latency_ms": 3.1,
                   "cost_usd": 0.0067, "failure_reason": None}],
        "grader_limitations": ["ties can fail exact matching"],
    }
    gate = {"gate": "PASS", "reasons": []}
    report = render_report(results, gate)
    assert "Pass: 7/8" in report
    assert "Release gate: PASS" in report
    assert "[PASS] a" in report
    assert "Failure handling (unknown-community): PASS" in report
