"""End-to-end tests on the shipped sample surface and the CLI/alerts path.

The sample CSV plants exactly three defects (see
``tools/generate_sample_surface.py``): one calendar violation, one
butterfly violation and one stale quote.
"""

import json

from vol_surface_checker.alerts import AlertSink
from vol_surface_checker.checks import run_all_checks
from vol_surface_checker.cli import main as cli_main

from conftest import SAMPLE_CSV


def test_sample_surface_flags_exactly_the_planted_violations(sample_surface):
    report = run_all_checks(sample_surface, max_age_hours=24.0)
    assert not report.ok
    assert report.counts_by_check() == {
        "calendar_arbitrage": 1,
        "butterfly_arbitrage": 1,
        "stale_quote": 1,
    }


def test_sample_calendar_violation_is_the_lone_t075_quote(sample_surface):
    report = run_all_checks(sample_surface, max_age_hours=24.0)
    cal = [v for v in report.violations if v.check == "calendar_arbitrage"]
    assert len(cal) == 1
    assert cal[0].strike == 100.0
    assert cal[0].expiry == 0.75


def test_sample_butterfly_violation_at_t2_strike_100(sample_surface):
    report = run_all_checks(sample_surface, max_age_hours=24.0)
    fly = [v for v in report.violations if v.check == "butterfly_arbitrage"]
    assert len(fly) == 1
    assert fly[0].strike == 100.0
    assert fly[0].expiry == 2.0


def test_alert_sink_emits_one_record_per_violation(sample_surface, tmp_path):
    alerts_file = tmp_path / "alerts.jsonl"
    sink = AlertSink(stream=None, file_path=alerts_file)
    report = run_all_checks(
        sample_surface, max_age_hours=24.0, on_violation=sink.emit
    )
    assert len(sink) == len(report.violations) == 3
    lines = alerts_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    records = [json.loads(line) for line in lines]
    assert all(r["alert"] == "surface_check_failed" for r in records)
    assert {r["check"] for r in records} == {
        "calendar_arbitrage",
        "butterfly_arbitrage",
        "stale_quote",
    }


def test_cli_end_to_end(tmp_path):
    report_path = tmp_path / "violations.json"
    alerts_path = tmp_path / "alerts.jsonl"
    exit_code = cli_main(
        [
            str(SAMPLE_CSV),
            "--max-age-hours",
            "24",
            "--report",
            str(report_path),
            "--alerts",
            str(alerts_path),
        ]
    )
    assert exit_code == 1  # violations found
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["ok"] is False
    assert payload["quotes_checked"] == 37
    assert len(payload["violations"]) == 3
    assert set(payload["rms_smile_error_by_expiry"]) == {
        "0.25",
        "0.5",
        "0.75",
        "1.0",
        "2.0",
    }
    assert len(alerts_path.read_text(encoding="utf-8").strip().splitlines()) == 3
