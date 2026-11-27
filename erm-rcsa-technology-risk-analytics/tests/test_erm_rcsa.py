"""Tests for the ERM / RCSA technology-risk analytics project."""

import csv
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from erm_rcsa.data import (
    generate_all,
    generate_kris,
    generate_loss_events,
    generate_risks,
)
from erm_rcsa.frameworks import assess
from erm_rcsa.kri import (
    breached_kris,
    emerging_kris,
    is_emerging_risk,
    kri_dashboard,
    kri_status,
)
from erm_rcsa.pipeline import (
    connect,
    load_data,
    python_loss_totals,
    reconcile,
    sql_loss_totals,
    top_loss_event,
)
from erm_rcsa.rcsa import (
    control_rating,
    controls_testing_summary,
    inherent_score,
    rcsa_assessment,
    residual_score,
    risk_band,
    toe_pass_rate,
)
from erm_rcsa.reporting import ExceptionQueue, dashboard_rows, render_report

ROOT = Path(__file__).resolve().parent.parent


def _risk(likelihood=4, impact=5):
    from erm_rcsa.data import Risk
    return Risk("R-X", "test risk", "technology", "IS", likelihood, impact)


def _control(design="Effective", sample_size=20, exceptions=1):
    from erm_rcsa.data import Control
    return Control("C-X", "R-X", "test control", design, sample_size, exceptions)


# --- RCSA scoring ---

def test_inherent_score_is_likelihood_times_impact():
    assert inherent_score(_risk(4, 5)) == 20
    assert inherent_score(_risk(1, 1)) == 1


def test_inherent_score_rejects_out_of_range_rating():
    with pytest.raises(ValueError):
        inherent_score(_risk(6, 3))
    with pytest.raises(ValueError):
        inherent_score(_risk(0, 3))


def test_risk_bands():
    assert risk_band(20) == "High"
    assert risk_band(16) == "High"
    assert risk_band(15) == "Medium"
    assert risk_band(9) == "Medium"
    assert risk_band(8) == "Low"


def test_toe_pass_rate():
    assert toe_pass_rate(_control(sample_size=25, exceptions=1)) == pytest.approx(0.96)
    assert toe_pass_rate(_control(sample_size=10, exceptions=10)) == 0.0


def test_toe_rejects_bad_sample():
    with pytest.raises(ValueError):
        toe_pass_rate(_control(sample_size=0, exceptions=0))
    with pytest.raises(ValueError):
        toe_pass_rate(_control(sample_size=10, exceptions=11))


def test_control_rating_needs_both_design_and_toe():
    assert control_rating(_control("Effective", 25, 1)) == "Effective"
    # Sound design but weak testing -> not Effective.
    assert control_rating(_control("Effective", 20, 4)) == "Needs Improvement"
    assert control_rating(_control("Ineffective", 10, 0)) == "Ineffective"
    assert control_rating(_control("Effective", 10, 3)) == "Ineffective"


def test_residual_score_drops_with_strong_control():
    risk = _risk(4, 5)  # inherent 20
    assert residual_score(risk, [_control("Effective", 25, 1)]) == pytest.approx(6.0)
    assert residual_score(risk, []) == 20.0
    # Weak ToE halves the design effectiveness: 20 * (1 - 0.35) = 13.0
    assert residual_score(risk, [_control("Effective", 20, 4)]) == pytest.approx(13.0)


def test_rcsa_assessment_covers_every_risk():
    data = generate_all()
    rows = rcsa_assessment(data["risks"], data["controls"])
    assert len(rows) == len(data["risks"]) == 14
    assert all("challenge" in r and r["challenge"] for r in rows)
    high = [r for r in rows if r["residual_band"] == "High"]
    assert high, "seeded register should contain at least one High residual risk"


def test_rcsa_flags_risk_with_no_control():
    rows = rcsa_assessment([_risk()], [])
    assert "no control" in rows[0]["challenge"]
    assert rows[0]["residual"] == 20.0


def test_controls_testing_summary_counts():
    data = generate_all()
    summary = controls_testing_summary(data["controls"])
    assert summary["total"] == 16
    assert summary["effective"] + summary["needs_improvement"] + summary["ineffective"] == 16
    assert "C-09" in summary["failing"]  # planted Ineffective control (restore test)


# --- KRI / KPI ---

def test_kri_status_higher_is_worse():
    kris = {k.kri_id: k for k in generate_kris()}
    assert kri_status(kris["K-01"]) == "BREACH"  # 24 unpatched criticals vs breach 20
    assert kri_status(kris["K-02"]) == "OK"  # 3.2% failed changes
    assert kri_status(kris["K-03"]) == "BREACH"  # 5 vendor SLA breaches vs breach 5


def test_kri_status_lower_is_worse():
    kris = {k.kri_id: k for k in generate_kris()}
    assert kri_status(kris["K-05"]) == "WARNING"  # 91% restore success vs warning 95
    assert kri_status(kris["K-06"]) == "OK"  # 91% reviews on time


def test_emerging_risk_detects_worsening_trend():
    kris = {k.kri_id: k for k in generate_kris()}
    assert is_emerging_risk(kris["K-01"])  # 12 -> 18 -> 24
    assert is_emerging_risk(kris["K-04"])  # 1.8 -> 2.6 -> 3.9
    assert not is_emerging_risk(kris["K-02"])  # flat/noisy, no trend


def test_dashboard_rows_and_breaches():
    rows = kri_dashboard(generate_kris())
    assert len(rows) == 8
    assert len(breached_kris(generate_kris())) == 2
    assert len(emerging_kris(generate_kris())) >= 3
    assert all(r["status"] in ("OK", "WARNING", "BREACH") for r in rows)


# --- Framework assessments ---

def _reqs():
    return generate_all()["framework_reqs"]


def test_framework_coverage_math():
    results = {r.req_id: "Met" for r in _reqs()}
    out = assess(_reqs(), results)
    assert out["overall_coverage"] == 100.0
    assert out["gaps"] == []


def test_framework_partial_counts_half():
    results = {r.req_id: "Partial" for r in _reqs()}
    out = assess(_reqs(), results)
    assert out["overall_coverage"] == 50.0
    assert len(out["gaps"]) == len(_reqs())


def test_framework_rejects_unknown_requirement_and_status():
    with pytest.raises(ValueError):
        assess(_reqs(), {"F-99": "Met"})
    with pytest.raises(ValueError):
        assess(_reqs(), {"F-01": "Done"})


def test_framework_gaps_name_the_open_items():
    results = {r.req_id: "Met" for r in _reqs()}
    results["F-03"] = "Not Met"
    out = assess(_reqs(), results)
    assert any(g["req_id"] == "F-03" and g["framework"] == "NIST" for g in out["gaps"])
    assert out["framework_coverage"]["NIST"] < 100.0


# --- Data / pipeline ---

def test_data_is_deterministic():
    assert generate_loss_events() == generate_loss_events()
    assert [r.risk_id for r in generate_risks()] == [r.risk_id for r in generate_risks()]


def test_planted_large_loss_is_top_event(tmp_path):
    data = generate_all()
    conn = connect(tmp_path / "t.db")
    load_data(conn, data)
    top = top_loss_event(conn)
    assert top["event_id"] == "LE-37"
    assert top["amount"] == 285000.00
    conn.close()


def test_python_and_sql_loss_totals_reconcile(tmp_path):
    data = generate_all()
    conn = connect(tmp_path / "t.db")
    load_data(conn, data)
    recon = reconcile(data["loss_events"], conn)
    assert recon["ok"] and recon["mismatches"] == {}
    assert recon["python"] == recon["sql"]
    assert set(recon["python"]) == {"operational", "compliance", "financial"}
    conn.close()


def test_negative_loss_is_rejected():
    from erm_rcsa.data import LossEvent
    with pytest.raises(ValueError):
        python_loss_totals([LossEvent("LE-99", "operational", "IT", -5.0, "2026-01-01")])


def test_sqlite_tables_hold_all_rows(tmp_path):
    data = generate_all()
    conn = connect(tmp_path / "t.db")
    load_data(conn, data)
    assert conn.execute("SELECT COUNT(*) FROM risks").fetchone()[0] == 14
    assert conn.execute("SELECT COUNT(*) FROM controls").fetchone()[0] == 16
    assert conn.execute("SELECT COUNT(*) FROM loss_events").fetchone()[0] == 37
    assert conn.execute("SELECT COUNT(*) FROM kri_readings").fetchone()[0] == 48
    conn.close()


# --- Reporting ---

def test_exception_queue_orders_most_severe_first():
    q = ExceptionQueue()
    q.add("WARNING", "KRI", "K-1", "warn")
    q.add("BREACH", "KRI", "K-2", "breach")
    q.add("Ineffective control", "Control", "C-1", "bad control")
    order = [i["severity"] for i in q.ordered()]
    assert order == ["BREACH", "Ineffective control", "WARNING"]


def test_exception_queue_rejects_unknown_severity():
    with pytest.raises(ValueError):
        ExceptionQueue().add("CRITICAL", "KRI", "K-1", "x")


def test_dashboard_rows_cover_rcsa_and_kris():
    data = generate_all()
    rows = dashboard_rows(rcsa_assessment(data["risks"], data["controls"]),
                          kri_dashboard(data["kris"]))
    assert len(rows) == 14 + 8
    assert {r["type"] for r in rows} == {"RCSA risk", "KRI"}


def test_render_report_names_breaches_and_top_loss(tmp_path):
    data = generate_all()
    rcsa_rows = rcsa_assessment(data["risks"], data["controls"])
    kri_rows = kri_dashboard(data["kris"])
    framework = assess(data["framework_reqs"], {r.req_id: "Met" for r in data["framework_reqs"]})
    conn = connect(tmp_path / "t.db")
    load_data(conn, data)
    recon = reconcile(data["loss_events"], conn)
    q = ExceptionQueue()
    q.add("BREACH", "KRI", "K-01", "unpatched criticals breached")
    text = render_report("2026-11-27", rcsa_rows, kri_rows, framework, recon,
                         top_loss_event(conn), q)
    assert "LE-37" in text and "K-01" in text and "PASS" in text
    conn.close()


def test_run_report_end_to_end(tmp_path):
    out = subprocess.run(
        [sys.executable, str(ROOT / "run_report.py")],
        cwd=ROOT, capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert "Loss reconciliation: PASS" in out.stdout
    reports = ROOT / "reports"
    for name in ("risk_report.txt", "rcsa_results.csv", "kri_dashboard.csv",
                 "dashboard.csv", "exceptions.csv", "framework_assessment.csv",
                 "signoff_checklist.csv"):
        assert (reports / name).exists(), name
    with open(reports / "kri_dashboard.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 8
    assert sum(1 for r in rows if r["status"] == "BREACH") == 2
    with open(reports / "rcsa_results.csv", newline="") as f:
        assert len(list(csv.DictReader(f))) == 14
