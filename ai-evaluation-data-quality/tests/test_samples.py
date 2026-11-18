"""Tests for the synthetic corpus and the end-to-end pipeline."""

from eval_quality.checks import run_all_checks
from eval_quality.report import render_json, render_text
from eval_quality.samples import build_corpus


def test_corpus_is_deterministic():
    assert build_corpus() == build_corpus()


def test_corpus_has_train_and_eval_splits():
    records = build_corpus()
    splits = {rec["split"] for rec in records}
    assert splits == {"train", "eval"}
    assert len(records) > 30


def test_corpus_covers_every_category_in_train():
    records = build_corpus()
    labels = {rec["label"] for rec in records if rec["split"] == "train"}
    assert {"violence", "self-harm", "hate", "sexual-content",
            "illicit-behavior", "safe"} <= labels


def test_pipeline_catches_all_six_planted_problems():
    report = run_all_checks(build_corpus())
    summary = report["summary"]
    assert summary["gate"] == "FAIL"
    assert summary["critical"] == 5
    assert summary["warnings"] == 1
    assert summary["findings_by_check"] == {
        "completeness": 1,
        "label-consistency": 2,
        "coverage": 1,
        "leakage": 1,
        "pii-scan": 1,
    }


def test_text_report_names_the_gate_and_each_finding():
    report = run_all_checks(build_corpus())
    text = render_text(report)
    assert "Quality gate: FAIL" in text
    assert "completeness: 1" in text
    assert "pii-scan: 1" in text
    assert "self-harm: 1" in text  # coverage line for the short category


def test_json_report_round_trips():
    import json

    report = run_all_checks(build_corpus())
    parsed = json.loads(render_json(report))
    assert parsed["summary"]["total_records"] == len(build_corpus())
    assert len(parsed["findings"]) == 6
