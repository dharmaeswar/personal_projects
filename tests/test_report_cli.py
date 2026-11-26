"""Tests for the briefing (text + JSON) and the CLI."""

import json

from safetyint.cli import main
from safetyint.data import generate_events, monthly_counts
from safetyint.report import (
    build_briefing,
    render_briefing_json,
    render_briefing_text,
)


def _briefing():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    return build_briefing(counts, exposure)


def test_briefing_has_all_sections():
    briefing = _briefing()
    assert briefing["latest_month"] == "2025-12"
    assert len(briefing["risk_ranking"]) == 6
    assert len(briefing["risk_matrix_latest_month"]) == 6
    assert any(
        r["category"] == "unstable-approach"
        for r in briefing["emerging_risks"]
    )


def test_briefing_text_names_top_risk_and_drift(capsys):
    text = render_briefing_text(_briefing())
    assert "SAFETY INTELLIGENCE BRIEFING" in text
    assert "unstable-approach" in text
    assert "per 10k flights" in text
    assert "synthetic demo data" in text


def test_briefing_json_round_trips():
    briefing = _briefing()
    parsed = json.loads(render_briefing_json(briefing))
    assert parsed["latest_month"] == briefing["latest_month"]
    assert len(parsed["risk_ranking"]) == 6


def test_cli_trends_lists_drift(capsys):
    assert main(["trends"]) == 0
    assert "unstable-approach" in capsys.readouterr().out


def test_cli_anomalies_runs(capsys):
    assert main(["anomalies"]) == 0
    assert "2025" in capsys.readouterr().out


def test_cli_risks_ranks_categories(capsys):
    assert main(["risks"]) == 0
    out = capsys.readouterr().out
    assert "1. " in out and "score" in out


def test_cli_briefing_text_and_json(capsys):
    assert main(["briefing"]) == 0
    assert "SAFETY INTELLIGENCE BRIEFING" in capsys.readouterr().out
    assert main(["briefing", "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["latest_month"] == "2025-12"
