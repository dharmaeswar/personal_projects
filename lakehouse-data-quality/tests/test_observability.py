"""Tests for data observability monitors (lakehouse/observability.py)."""

from __future__ import annotations

import pandas as pd

from lakehouse.observability import (
    check_freshness,
    check_schema_drift,
    check_volume,
    render_observability_report,
    run_observability,
    summarize,
)


def _ts(text: str) -> pd.Timestamp:
    return pd.Timestamp(text, tz="UTC")


def test_freshness_ok_and_alert():
    ok = check_freshness(_ts("2026-11-17 10:00"), _ts("2026-11-17 10:10"), sla_minutes=60)
    assert ok.status == "ok"
    alert = check_freshness(_ts("2026-11-17 10:00"), _ts("2026-11-17 12:00"), sla_minutes=60)
    assert alert.status == "alert"
    assert "120.0 minutes" in alert.detail


def test_volume_ok_warning_alert():
    history = [100, 102, 98, 101, 99]  # mean 100, std ~1.58
    assert check_volume(100, history).status == "ok"
    assert check_volume(104, history).status == "warning"
    assert check_volume(110, history).status == "alert"
    assert check_volume(90, history).status == "alert"


def test_volume_no_baseline_yet():
    result = check_volume(50, [48, 52])
    assert result.status == "ok"
    assert "no baseline" in result.detail


def test_volume_flat_baseline():
    assert check_volume(40, [40, 40, 40]).status == "ok"
    assert check_volume(41, [40, 40, 40]).status == "alert"


def test_schema_drift():
    df = pd.DataFrame({"a": [1], "b": [2], "c": [3]})
    assert check_schema_drift(df, ["a", "b", "c"]).status == "ok"
    missing = check_schema_drift(df, ["a", "b", "c", "d"])
    assert missing.status == "alert"
    assert "d" in missing.detail
    extra = check_schema_drift(df, ["a", "b"])
    assert extra.status == "warning"
    assert "c" in extra.detail


def test_run_observability_healthy_table():
    df = pd.DataFrame(
        {
            "event_id": ["E1", "E2"],
            "event_time": pd.to_datetime(["2026-11-17 10:00", "2026-11-17 10:05"], utc=True),
            "value": [10, 20],
        }
    )
    results = run_observability(
        df,
        "event_time",
        _ts("2026-11-17 10:10"),
        ["event_id", "event_time", "value"],
        [2, 3, 1, 2, 2],
    )
    assert [r.status for r in results] == ["ok", "ok", "ok"]
    assert summarize(results)["healthy"] is True


def test_run_observability_unhealthy_table():
    df = pd.DataFrame(
        {
            "event_id": ["E1"],
            "event_time": pd.to_datetime(["2026-11-17 08:00"], utc=True),
        }
    )
    results = run_observability(
        df,
        "event_time",
        _ts("2026-11-17 12:00"),
        ["event_id", "event_time", "value"],
        [100, 102, 98, 101, 99],
    )
    statuses = [r.status for r in results]
    assert statuses[0] == "alert"  # freshness: 4 hours old
    assert statuses[2] == "alert"  # schema: missing "value"
    assert summarize(results)["healthy"] is False


def test_render_report():
    df = pd.DataFrame({"event_time": pd.to_datetime(["2026-11-17 10:00"], utc=True)})
    results = run_observability(
        df, "event_time", _ts("2026-11-17 10:10"), ["event_time"], [1, 2, 1, 1]
    )
    report = render_observability_report(results)
    assert "DATA OBSERVABILITY REPORT" in report
    assert "healthy: True" in report
