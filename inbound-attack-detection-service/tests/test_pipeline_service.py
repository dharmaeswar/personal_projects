"""Tests for the pipeline, the service handlers, and the CLI entry point."""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from detection.pipeline import format_report, generate_dataset, run_pipeline
from detection.service import score_message_payload, triage_message_payload
from tests.test_features import LEGIT, PHISH

BASE = Path(__file__).resolve().parent.parent


def test_dataset_is_seeded_and_reproducible():
    a = generate_dataset(seed=42)
    b = generate_dataset(seed=42)
    assert a == b
    assert len(a) == 150
    assert sum(1 for m in a if m["label"] == 1) == 65


def test_dataset_segments_cover_all_kinds():
    messages = generate_dataset(seed=1)
    segments = {m["segment"] for m in messages}
    assert segments == {"legitimate", "phishing", "bec", "bulk"}


def test_pipeline_writes_db_and_json_report(tmp_path):
    report = run_pipeline(
        seed=42, db_path=tmp_path / "out.db", report_path=tmp_path / "out.json"
    )
    assert (tmp_path / "out.json").exists()
    assert json.loads((tmp_path / "out.json").read_text())["overall"]["n"] == 150
    conn = sqlite3.connect(tmp_path / "out.db")
    rows = conn.execute("SELECT COUNT(*) FROM scored_messages").fetchone()[0]
    conn.close()
    assert rows == 150
    assert 0.0 <= report["overall"]["precision"] <= 1.0
    assert report["overall"]["roc_auc"] > 0.8


def test_pipeline_report_has_segments_and_sweep(tmp_path):
    report = run_pipeline(
        seed=42, db_path=tmp_path / "o.db", report_path=tmp_path / "o.json"
    )
    assert set(report["by_segment"]) == {"legitimate", "phishing", "bec", "bulk"}
    assert len(report["threshold_sweep"]) == 19
    assert set(report["triage_counts"]) == {"quarantine", "escalate", "allow"}


def test_format_report_is_readable(tmp_path):
    report = run_pipeline(
        seed=42, db_path=tmp_path / "o.db", report_path=tmp_path / "o.json"
    )
    text = format_report(report)
    assert "Precision" in text and "Recall" in text and "ROC-AUC" in text
    assert "phishing" in text


def test_score_endpoint_flags_phish():
    status, body = score_message_payload(PHISH)
    assert status == 200
    assert body["label"] == "attack"
    assert body["score"] >= 0.5


def test_score_endpoint_allows_legit():
    status, body = score_message_payload(LEGIT)
    assert status == 200
    assert body["label"] == "legitimate"


def test_score_endpoint_rejects_bad_payload():
    assert score_message_payload({})[0] == 400
    assert score_message_payload({"subject": "no sender"})[0] == 400
    assert triage_message_payload(None)[0] == 400


def test_triage_endpoint_returns_verdict():
    status, body = triage_message_payload(PHISH)
    assert status == 200
    assert body["triage"]["verdict"] == "quarantine"
    assert "score" in body


def test_run_detection_cli_generates_report(tmp_path):
    # Run the real entry point from a temp copy-free invocation: it writes
    # next to run_detection.py, so run it and check the artefacts exist.
    result = subprocess.run(
        [sys.executable, "run_detection.py"],
        cwd=BASE, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "Precision" in result.stdout
    assert (BASE / "detection_report.json").exists()
    assert (BASE / "detection_results.db").exists()
    report = json.loads((BASE / "detection_report.json").read_text())
    assert report["overall"]["n"] == 150
