"""Tests for the data quality agent (detection + diagnosis)."""

from agent_eval.data_quality import (check_duplicates, check_freshness,
                                     check_null_rate, check_schema,
                                     check_volume, run_quality_sweep)


def _rows(n, **overrides):
    rows = []
    for i in range(n):
        row = {"id": i, "score": 10 + i, "community": "python"}
        row.update(overrides.get(i, {}))
        rows.append(row)
    return rows


def test_fresh_within_sla_returns_none():
    assert check_freshness(last_load_day=29, today_day=29, sla_days=1) is None
    assert check_freshness(last_load_day=28, today_day=29, sla_days=1) is None


def test_stale_load_is_warning_then_critical():
    warn = check_freshness(last_load_day=27, today_day=29, sla_days=1)
    assert warn["type"] == "stale_load" and warn["severity"] == "warning"
    crit = check_freshness(last_load_day=25, today_day=29, sla_days=1)
    assert crit["severity"] == "critical"
    assert "likely_cause" in crit and "recommended_fix" in crit


def test_volume_within_tolerance_returns_none():
    assert check_volume(95, 100) is None
    assert check_volume(118, 100) is None


def test_volume_drop_and_spike():
    drop = check_volume(40, 100)
    assert drop["type"] == "volume_drop" and drop["severity"] == "critical"
    spike = check_volume(250, 100)
    assert spike["type"] == "volume_spike"


def test_null_rate_below_threshold_returns_none():
    assert check_null_rate(_rows(100), "score", threshold=0.05) is None


def test_null_spike_reports_rate_and_fix():
    rows = _rows(20)
    for i in range(6):
        rows[i]["score"] = None
    issue = check_null_rate(rows, "score", threshold=0.05)
    assert issue["type"] == "null_spike"
    assert "30.0%" in issue["detail"]
    assert issue["severity"] == "critical"


def test_duplicates_detected_on_key():
    rows = _rows(5)
    rows.append({"id": 2, "score": 99, "community": "python"})
    issue = check_duplicates(rows, "id")
    assert issue is not None and issue["type"] == "duplicate_keys"
    assert check_duplicates(_rows(5), "id") is None


def test_schema_drift_added_and_removed():
    drift = check_schema(["id", "score", "extra"],
                         ["id", "score", "community"])
    assert drift["type"] == "schema_drift"
    assert "extra" in drift["detail"] and "community" in drift["detail"]
    assert check_schema(["id", "score"], ["id", "score"]) is None


def test_clean_sweep_reports_ok():
    result = run_quality_sweep({
        "table": "posts", "today_day": 29, "last_load_day": 29,
        "sla_days": 1, "row_count": 100, "expected_rows": 100,
        "columns": ["id", "score"], "expected_columns": ["id", "score"],
        "rows": _rows(10), "key": "id", "null_columns": ["score"],
    })
    assert result["status"] == "ok" and result["issue_count"] == 0


def test_sweep_collects_every_issue_and_worst_severity():
    rows = _rows(10)
    rows.append({"id": 3, "score": None, "community": "python"})
    result = run_quality_sweep({
        "table": "posts", "today_day": 29, "last_load_day": 24,
        "sla_days": 1, "row_count": 11, "expected_rows": 100,
        "columns": ["id", "score"], "expected_columns": ["id", "score"],
        "rows": rows, "key": "id", "null_columns": [("score", 0.05)],
    })
    types = {i["type"] for i in result["issues"]}
    assert types == {"stale_load", "volume_drop", "duplicate_keys",
                     "null_spike"}
    assert result["status"] == "critical"
    assert result["issue_count"] == 4
