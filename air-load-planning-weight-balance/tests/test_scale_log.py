import pytest

from airload.scale_log import ScaleLog, ScaleReading


def _log_with_readings() -> ScaleLog:
    log = ScaleLog()
    log.record(ScaleReading("SCALE-1", "2026-11-24T10:15:00Z", "cargo:FWD:AKE12345", 8_510.0))
    log.record(ScaleReading("SCALE-2", "2026-11-24T10:17:00Z", "cargo:AFT:AKE12346", 7_190.0))
    return log


def test_matching_readings_reconcile_cleanly():
    log = _log_with_readings()
    planned = {"cargo:FWD:AKE12345": 8_500.0, "cargo:AFT:AKE12346": 7_200.0}
    assert log.reconcile(planned) == []


def test_drift_beyond_tolerance_is_flagged():
    log = _log_with_readings()
    planned = {"cargo:FWD:AKE12345": 8_500.0, "cargo:AFT:AKE12346": 6_000.0}
    findings = log.reconcile(planned)
    assert len(findings) == 1
    assert "cargo:AFT:AKE12346" in findings[0]
    assert "+1,190 lb" in findings[0]


def test_reading_with_no_planned_item_is_flagged():
    log = _log_with_readings()
    log.record(ScaleReading("SCALE-3", "2026-11-24T10:19:00Z", "cargo:BULK:STOWAWAY", 500.0))
    planned = {"cargo:FWD:AKE12345": 8_500.0, "cargo:AFT:AKE12346": 7_200.0}
    findings = log.reconcile(planned)
    assert any("STOWAWAY" in f and "no planned item" in f for f in findings)


def test_negative_scale_weight_rejected():
    with pytest.raises(ValueError):
        ScaleReading("SCALE-1", "2026-11-24T10:15:00Z", "cargo:FWD:AKE1", -5.0)


def test_total_for_sums_only_matching_item():
    log = _log_with_readings()
    assert log.total_for("cargo:FWD:AKE12345") == 8_510.0
    assert log.total_for("cargo:FWD:OTHER") == 0.0
