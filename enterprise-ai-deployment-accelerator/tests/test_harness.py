"""Tests for the eval harness, readiness gate and playbook."""

import json

from enterprise_ai_deployment import (
    Agent, DocStore, Document, EvalCase, ReadinessGate,
    build_enterprise_tools, evaluate_readiness, generate_playbook,
    run_eval, UseCase,
)


def _agent():
    store = DocStore()
    store.add(Document("POL-001", "Password Reset Policy",
                       "Employees reset passwords through the self-service "
                       "portal. A reset link expires after 30 minutes."))
    return Agent(store, build_enterprise_tools(store))


def _cases():
    return [
        EvalCase("c1", "How do I reset my password?",
                 ["self-service portal", "30 minutes"]),
        EvalCase("c2", "What is the refund policy for cancelled flights?",
                 ["refund"]),
    ]


def test_harness_scores_each_case(tmp_path):
    results, summary = run_eval(_agent(), _cases(),
                                log_path=str(tmp_path / "log.jsonl"))
    assert summary.total == 2
    assert summary.passed == 1
    assert summary.pass_rate == 0.5
    assert results[0].grade.passed is True
    assert results[1].grade.passed is False  # ungrounded: escalates


def test_harness_writes_jsonl_log(tmp_path):
    log = tmp_path / "log.jsonl"
    run_eval(_agent(), _cases(), log_path=str(log))
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(lines) == 3  # 2 cases + 1 summary record
    assert lines[-1]["summary"]["total"] == 2


def test_gate_fails_on_low_pass_rate():
    _, summary = run_eval(_agent(), _cases())
    report = evaluate_readiness(summary, ReadinessGate())
    assert report.passed is False
    failed = [c for c in report.checks if not c["passed"]]
    assert any(c["name"] == "eval pass rate" for c in failed)


def test_gate_passes_on_clean_run():
    _, summary = run_eval(_agent(), _cases()[:1])
    report = evaluate_readiness(summary, ReadinessGate())
    assert report.passed is True


def test_playbook_records_verdict_and_checks():
    _, summary = run_eval(_agent(), _cases()[:1])
    report = evaluate_readiness(summary, ReadinessGate())
    case = UseCase("Support knowledge assistant", "IT support",
                   "Answer employee questions from policy documents.",
                   value=8, data_readiness=9, risk=3)
    text = generate_playbook(case, summary, report)
    assert "READY FOR PRODUCTION" in text
    assert "eval pass rate" in text
    assert "Rollout steps" in text
