"""Tests for the Systematic Research Agent Platform."""

import math

import pytest

from research_platform.agents import (
    compose,
    execute,
    plan,
    retrieve,
    validate,
)
from research_platform.chunking import chunk_document
from research_platform.corpus import get_document, get_documents
from research_platform.evaluate import (
    EVAL_TASKS,
    regression_report,
    run_evaluation,
    score_run,
    summarize,
)
from research_platform.knowledge_layer import KnowledgeLayer
from research_platform.orchestrator import ResearchRun
from research_platform.tools import ToolError, ToolRegistry


def _tools():
    return ToolRegistry(KnowledgeLayer(get_documents()))


# --- chunking ---

def test_chunking_keeps_source_metadata():
    doc = get_document("RN-MOM-01")
    chunks = chunk_document(doc)
    assert chunks
    assert all(c["doc_id"] == "RN-MOM-01" for c in chunks)
    assert all(c["kind"] == "research" for c in chunks)
    assert all(len(c["text"].split()) <= 120 for c in chunks)


def test_chunking_short_text_is_one_passage():
    doc = {"id": "X", "kind": "research", "title": "T", "text": "One short sentence."}
    assert len(chunk_document(doc)) == 1


# --- knowledge layer ---

def test_retrieval_finds_momentum_note_first():
    layer = KnowledgeLayer(get_documents())
    results = layer.search("momentum 252-day return", kind="research")
    assert results
    assert results[0]["doc_id"] == "RN-MOM-01"


def test_retrieval_kind_filter():
    layer = KnowledgeLayer(get_documents())
    results = layer.search("momentum factor return volatility Sharpe", kind="data")
    assert results
    assert all(r["kind"] == "data" for r in results)
    assert results[0]["doc_id"] == "DATA-MOM-01"


def test_retrieval_empty_query_returns_nothing():
    layer = KnowledgeLayer(get_documents())
    assert layer.search("the and of") == []


# --- tool registry (MCP-style) ---

def test_unknown_tool_raises():
    with pytest.raises(ToolError):
        _tools().call("no_such_tool", {})


def test_missing_parameter_raises():
    with pytest.raises(ToolError):
        _tools().call("search_knowledge", {})


def test_read_code_returns_snippet():
    result = _tools().call("read_code", {"doc_id": "CODE-MOM-01"})
    assert "momentum_signal" in result["text"]


def test_read_code_unknown_id_raises():
    with pytest.raises(ToolError):
        _tools().call("read_code", {"doc_id": "CODE-NOPE-01"})


def test_compute_statistic_mean():
    result = _tools().call(
        "compute_statistic", {"series": "momentum", "statistic": "mean"})
    assert result["value"] == pytest.approx(0.000246, abs=1e-6)


def test_compute_statistic_sharpe_is_finite():
    result = _tools().call(
        "compute_statistic", {"series": "carry", "statistic": "sharpe"})
    assert math.isfinite(result["value"])


def test_validate_number_matches_ground_truth():
    result = _tools().call(
        "validate_number", {"label": "momentum sharpe", "value": 0.54})
    assert result["checked"] is True
    assert result["match"] is True


def test_validate_number_catches_wrong_value():
    result = _tools().call(
        "validate_number", {"label": "momentum sharpe", "value": 0.99})
    assert result["match"] is False


def test_tool_calls_are_logged():
    tools = _tools()
    tools.call("search_knowledge", {"query": "momentum"})
    assert len(tools.call_log) == 1
    assert tools.call_log[0]["tool"] == "search_knowledge"


# --- agents ---

def test_planner_decomposes_momentum_question():
    subtasks = plan("What is the momentum signal and what did it return?")
    assert any(s["topic"] == "momentum" for s in subtasks)


def test_planner_falls_back_for_unknown_question():
    subtasks = plan("What is the weather in Boston?")
    assert subtasks[0]["topic"] == "general"


def test_compose_without_evidence_refuses_to_invent():
    answer = compose("Unknown topic?", [{"topic": "general", "description": ""}], [], [])
    assert "Not covered" in answer["text"]
    assert answer["citations"] == []


def test_validator_passes_grounded_answer():
    tools = _tools()
    answer = {"text": "x", "citations": ["DATA-MOM-01"],
              "claims": [{"label": "momentum sharpe", "value": 0.54}]}
    assert validate(tools, answer)["passed"] is True


def test_validator_fails_wrong_number():
    tools = _tools()
    answer = {"text": "x", "citations": ["DATA-MOM-01"],
              "claims": [{"label": "momentum sharpe", "value": 0.99}]}
    assert validate(tools, answer)["passed"] is False


# --- orchestrator end to end ---

def test_full_run_is_grounded_and_cited():
    result = ResearchRun(
        "What is the momentum signal and what did the momentum factor return?"
    ).run()
    assert result["validation"]["passed"] is True
    assert "RN-MOM-01" in result["answer"]["citations"]
    assert "DATA-MOM-01" in result["answer"]["citations"]
    assert "read_code" in result["tools_used"]
    assert "compute_statistic" in result["tools_used"]


def test_run_without_validator_has_no_validation():
    result = ResearchRun("How does FX carry work?", use_validator=False).run()
    assert result["validation"] is None
    assert "RN-CARRY-01" in result["answer"]["citations"]


def test_repeat_run_is_reproducible():
    question = "How does volatility targeting keep the portfolio at its target?"
    first = ResearchRun(question).run()
    second = ResearchRun(question).run()
    assert first["answer"]["text"] == second["answer"]["text"]


# --- evaluation harness ---

def test_eval_tasks_all_scored():
    scored = run_evaluation(use_validator=True)
    assert len(scored) == len(EVAL_TASKS)
    assert all(s["grounded"] for s in scored)
    assert all(s["citation_coverage"] == 1.0 for s in scored)
    assert all(s["reproducible"] for s in scored)


def test_regression_report_gate_passes():
    report = regression_report()
    assert report["release_gate_passed"] is True
    assert report["improved"]["summary"]["grounded_rate"] == 1.0
    assert report["baseline"]["summary"]["grounded_rate"] == 0.0


def test_summarize_rates():
    summary = summarize([
        {"grounded": True, "citation_coverage": 1.0, "figures_correct": True,
         "tool_accuracy": 1.0, "reproducible": True},
        {"grounded": False, "citation_coverage": 0.5, "figures_correct": False,
         "tool_accuracy": 0.5, "reproducible": True},
    ])
    assert summary["grounded_rate"] == 0.5
    assert summary["mean_citation_coverage"] == 0.75
    assert summary["reproducible_rate"] == 1.0
