"""Tests for the AI-generated-code change gate."""

from agent_eval.change_gate import (
    ChangedFile, CodeChange, build_sample_changes, gate_change,
    run_change_gate_eval)


def _clean_change():
    return CodeChange(
        "T-1", "agent",
        [ChangedFile("pricing/engine.py",
                     "def discount(price, rate):\n"
                     "    \"\"\"Apply a discount rate to a price.\"\"\"\n"
                     "    return round(price * (1 - rate), 2)\n",
                     hot_path=True)],
        tests_run=(4, 4),
        retrieval_context=[{"source": "pricing/engine.py",
                            "snippet": "engine.py pricing helpers"}])


def test_clean_change_passes_with_full_score():
    verdict = gate_change(_clean_change())
    assert verdict.passed
    assert verdict.score == 100
    assert verdict.failures == []


def test_syntax_error_fails_compile_stage():
    change = CodeChange("T-2", "agent",
                        [ChangedFile("a.py", "def broken(\n")],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any("compile" in c.stage for c in verdict.checks
               if not c.passed)


def test_eval_call_fails_safety_stage():
    change = CodeChange("T-3", "agent",
                        [ChangedFile("a.py", "def run(cmd):\n"
                                            "    return eval(cmd)\n")],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "safety" and not c.passed
               for c in verdict.checks)
    assert any("eval" in f for f in verdict.failures)


def test_hardcoded_password_fails_safety_stage():
    change = CodeChange("T-4", "agent",
                        [ChangedFile("a.py", "password = \"hunter2\"\n")],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "safety" and not c.passed
               for c in verdict.checks)


def test_shell_true_fails_safety_stage():
    change = CodeChange("T-5", "agent",
                        [ChangedFile("a.py",
                                     "import subprocess\n\n\n"
                                     "def run(cmd):\n"
                                     "    return subprocess.call(cmd, "
                                     "shell=True)\n")],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "safety" and not c.passed
               for c in verdict.checks)


def test_unused_import_fails_static_analysis():
    change = CodeChange("T-6", "agent",
                        [ChangedFile("a.py", "import os\n\n\n"
                                            "def f():\n"
                                            "    return 1\n")],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "static-analysis" and not c.passed
               for c in verdict.checks)


def test_long_line_fails_style_stage():
    change = CodeChange("T-7", "agent",
                        [ChangedFile("a.py", "x = \"" + "a" * 130 + "\"\n")],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "style" and not c.passed
               for c in verdict.checks)


def test_hot_path_deep_loop_fails_performance_stage():
    change = CodeChange("T-8", "agent",
                        [ChangedFile("a.py",
                                     "def f(rows):\n"
                                     "    total = 0\n"
                                     "    for r in rows:\n"
                                     "        for c in r:\n"
                                     "            for v in c:\n"
                                     "                total += v\n"
                                     "    return total\n",
                                     hot_path=True)],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "performance" and not c.passed
               for c in verdict.checks)


def test_deep_loop_outside_hot_path_passes_performance():
    change = CodeChange("T-9", "agent",
                        [ChangedFile("a.py",
                                     "def f(rows):\n"
                                     "    total = 0\n"
                                     "    for r in rows:\n"
                                     "        for c in r:\n"
                                     "            for v in c:\n"
                                     "                total += v\n"
                                     "    return total\n")],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert verdict.passed


def test_no_tests_run_fails_tests_stage():
    change = _clean_change()
    change.tests_run = (0, 0)
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "tests" and not c.passed
               for c in verdict.checks)


def test_failing_tests_fail_tests_stage():
    change = _clean_change()
    change.tests_run = (1, 3)
    verdict = gate_change(change)
    assert not verdict.passed
    assert any("1/3" in f for f in verdict.failures)


def test_missing_retrieval_context_fails_context_stage():
    change = _clean_change()
    change.retrieval_context = []
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "retrieval-context" and not c.passed
               for c in verdict.checks)


def test_empty_change_fails():
    verdict = gate_change(CodeChange("T-10", "agent", []))
    assert not verdict.passed
    assert "empty change" in verdict.failures[0]


def test_score_is_bounded_and_deducts_per_failure():
    change = CodeChange("T-11", "agent",
                        [ChangedFile("a.py", "password = \"x\"\n")],
                        tests_run=(0, 0),
                        retrieval_context=[])
    verdict = gate_change(change)
    assert 0 <= verdict.score <= 100
    # safety (30) + tests (20) + retrieval-context (10) = 60 deducted.
    assert verdict.score == 40


def test_oversized_change_fails_performance_stage():
    big = "\n".join(f"VALUE_{i} = {i}" for i in range(600))
    change = CodeChange("T-12", "agent",
                        [ChangedFile("a.py", big)],
                        tests_run=(1, 1),
                        retrieval_context=[{"source": "a.py",
                                            "snippet": "a.py helpers"}])
    verdict = gate_change(change)
    assert not verdict.passed
    assert any(c.stage == "performance" and not c.passed
               for c in verdict.checks)


def test_sample_changes_are_deterministic():
    first = build_sample_changes()
    second = build_sample_changes()
    assert [c.change_id for c in first] == [c.change_id for c in second]
    assert len(first) == 5


def test_sample_eval_verdicts():
    report = run_change_gate_eval(build_sample_changes())
    verdicts = {c["change_id"]: c for c in report["changes"]}
    assert verdicts["CHG-101"]["passed"] is True
    assert verdicts["CHG-101"]["score"] == 100
    assert verdicts["CHG-102"]["passed"] is False
    assert verdicts["CHG-103"]["passed"] is False
    assert verdicts["CHG-104"]["passed"] is False
    assert verdicts["CHG-105"]["passed"] is False
    assert report["total"] == 5
    assert report["passed"] == 1
    assert report["pass_rate"] == 0.2
    assert report["verdict"] == "FAIL"


def test_verdict_dict_round_trips():
    verdict = gate_change(_clean_change())
    data = verdict.as_dict()
    assert data["change_id"] == "T-1"
    assert data["passed"] is True
    assert len(data["checks"]) == 7
    assert all("stage" in c and "passed" in c for c in data["checks"])
