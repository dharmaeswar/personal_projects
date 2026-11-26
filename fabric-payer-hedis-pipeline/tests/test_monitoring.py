"""Tests for production-support health monitoring."""

from fabric_hedis import medallion, monitoring


def _conn(tmp_path):
    return medallion.connect(tmp_path / "db.sqlite")


def test_healthy_run_has_no_alerts(tmp_path):
    conn = _conn(tmp_path)
    stats = {"bronze_claims": 186, "silver_claims": 179, "quarantined": 6}
    assert monitoring.health_checks(conn, "2026-10", stats) == []
    assert monitoring.summarize_alerts([]) == "HEALTHY: no alerts"


def test_quarantine_rate_alert(tmp_path):
    conn = _conn(tmp_path)
    stats = {"bronze_claims": 100, "silver_claims": 90, "quarantined": 10}
    alerts = monitoring.health_checks(conn, "2026-10", stats)
    assert len(alerts) == 1
    assert alerts[0]["check"] == "quarantine_rate"
    assert "10.0%" in alerts[0]["detail"]


def test_row_count_swing_alert(tmp_path):
    conn = _conn(tmp_path)
    medallion.save_run_stats(conn, "2026-09", {
        "bronze_claims": 100, "silver_claims": 95, "quarantined": 5})
    stats = {"bronze_claims": 186, "silver_claims": 179, "quarantined": 6}
    alerts = monitoring.health_checks(conn, "2026-10", stats)
    assert any(a["check"] == "row_count_swing" for a in alerts)


def test_small_swing_is_not_an_alert(tmp_path):
    conn = _conn(tmp_path)
    medallion.save_run_stats(conn, "2026-09", {
        "bronze_claims": 180, "silver_claims": 175, "quarantined": 5})
    stats = {"bronze_claims": 186, "silver_claims": 179, "quarantined": 6}
    alerts = monitoring.health_checks(conn, "2026-10", stats)
    assert alerts == []


def test_failed_step_raises_critical_alert(tmp_path):
    conn = _conn(tmp_path)
    monitoring.record_run(conn, "monthly-2026-10", "load_bronze",
                          "failed", "checksum mismatch on claims file")
    stats = {"bronze_claims": 186, "silver_claims": 179, "quarantined": 6}
    alerts = monitoring.health_checks(conn, "2026-10", stats)
    assert any(a["severity"] == "critical"
               and "load_bronze" in a["detail"] for a in alerts)
