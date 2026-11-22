import json
from pathlib import Path

import pandas as pd
import pytest

from trade_reg_analytics.data import WarehouseConfig, build_positions, generate_orders_trades
from trade_reg_analytics.patterns import run_all_detectors
from trade_reg_analytics.report import findings_summary, write_report
from trade_reg_analytics.stats import daily_volume


@pytest.fixture(scope="module")
def artefacts(tmp_path_factory):
    orders, trades = generate_orders_trades(WarehouseConfig(seed=42, days=5))
    positions = build_positions(trades)
    findings = run_all_detectors(orders, trades, positions)
    out = tmp_path_factory.mktemp("report")
    files = write_report(findings, daily_volume(trades), out)
    return findings, files


def test_summary_counts(artefacts):
    findings, _ = artefacts
    summary = findings_summary(findings)
    assert summary["total_findings"] == len(findings)
    assert summary["by_pattern"]["wash_trade"]["count"] >= 5
    assert summary["by_pattern"]["spoofing"]["count"] >= 5
    assert 0 < summary["top_severity"] <= 100


def test_summary_empty_findings():
    empty = pd.DataFrame(columns=["pattern", "severity"])
    summary = findings_summary(empty)
    assert summary == {"total_findings": 0, "by_pattern": {}, "top_severity": 0}


def test_all_report_files_written(artefacts):
    _, files = artefacts
    for name, path in files.items():
        assert Path(path).exists(), f"missing {name}"
        assert Path(path).stat().st_size > 0


def test_summary_json_matches_report(artefacts):
    _, files = artefacts
    summary = json.loads(Path(files["summary"]).read_text())
    assert summary["total_findings"] > 0
    report = Path(files["report"]).read_text()
    assert "Regulatory Trade-Pattern Review" in report
    assert "wash_trade" in report


def test_chart_svg_lists_patterns(artefacts):
    _, files = artefacts
    svg = Path(files["chart"]).read_text()
    assert svg.startswith("<svg")
    assert "wash_trade" in svg
    assert "spoofing" in svg


def test_findings_csv_roundtrip(artefacts):
    findings, files = artefacts
    reloaded = pd.read_csv(files["findings"])
    assert len(reloaded) == len(findings)
    assert set(reloaded["pattern"]) == set(findings["pattern"])
