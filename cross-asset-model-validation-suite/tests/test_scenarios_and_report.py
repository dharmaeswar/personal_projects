"""Tests for YAML scenario expansion and the summary report writers."""

import csv
import json
from pathlib import Path

from model_validation_suite.invariants import run_suite
from model_validation_suite.report import summarise, write_csv, write_json
from model_validation_suite.scenarios import expand_scenarios, load_config

CONFIG = Path(__file__).resolve().parent.parent / "configs" / "scenarios.yaml"


def test_grid_expansion_counts():
    scenarios = expand_scenarios(load_config(CONFIG))
    by_asset = {}
    for s in scenarios:
        by_asset[s["asset_class"]] = by_asset.get(s["asset_class"], 0) + 1
    # rates: 4 parallel shifts; fx: 3 spot x 3 vol; equity: 3 spot x 3 vol.
    assert by_asset == {"rates": 4, "fx": 9, "equity": 9}
    assert len({s["id"] for s in scenarios}) == len(scenarios)  # ids unique


def test_scenario_contexts_are_fully_resolved():
    for s in expand_scenarios(load_config(CONFIG)):
        assert s["context"]["tolerances"]["parity"] > 0
        if s["asset_class"] == "equity":
            assert s["context"]["vol"] > 0
            assert s["context"]["spot"] > 0


def test_report_writers_round_trip(tmp_path):
    results = run_suite(expand_scenarios(load_config(CONFIG)))
    summary = write_json(results, tmp_path / "summary.json", config_name="scenarios.yaml")
    write_csv(results, tmp_path / "summary.csv")

    payload = json.loads((tmp_path / "summary.json").read_text())
    assert payload["total_checks"] == len(results) == summary["total_checks"]
    assert payload["failed"] == 0
    assert payload["breaches"] == []

    with open(tmp_path / "summary.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == len(results)
    assert {row["status"] for row in rows} == {"PASS"}
    assert set(rows[0]) == {"scenario_id", "asset_class", "invariant",
                            "status", "measured", "limit", "detail"}


def test_summarise_counts_by_asset_class():
    results = run_suite(expand_scenarios(load_config(CONFIG)))
    summary = summarise(results)
    assert summary["pass_rate"] == 1.0
    assert set(summary["by_asset_class"]) == {"rates", "fx", "equity"}
