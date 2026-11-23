"""End-to-end tests: full run, summary, and CLI report file."""

import json

from investment_data_validation import __main__ as runner


def test_run_all_covers_four_datasets():
    reports = runner.run_all()
    assert set(reports) == {
        "security_master", "trades", "yield_curve",
        "warehouse_reconciliation",
    }


def test_seeded_data_has_failures_to_catch():
    reports = runner.run_all()
    assert reports["security_master"].failed == 5
    assert reports["trades"].failed == 7
    assert reports["yield_curve"].failed == 2
    assert reports["warehouse_reconciliation"].failed >= 3


def test_summary_is_json_serializable():
    summary = runner.summarize(runner.run_all())
    assert json.dumps(summary)
    assert summary["overall_pass"] is False
    assert summary["total_failed"] > 0


def test_cli_writes_report_file(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    runner.main()
    out = capsys.readouterr().out
    assert "OVERALL:" in out
    report = json.loads((tmp_path / "validation_report.json").read_text())
    assert report["total_failed"] > 0
    assert len(report["datasets"]) == 4
