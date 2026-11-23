"""Tests for yield-curve validations."""

from investment_data_validation.data import AS_OF, build_yield_curves
from investment_data_validation.yields import (
    EXPECTED_TENORS,
    validate_yield_curve,
)


def _findings(report, check, record_id):
    return [f for f in report.findings
            if f.check == check and f.record_id == record_id]


def test_missing_tenor_flagged():
    prior, current = build_yield_curves()
    report = validate_yield_curve(current, prior, AS_OF)
    assert _findings(report, "tenor_present", "7Y")


def test_stale_point_flagged():
    prior, current = build_yield_curves()
    report = validate_yield_curve(current, prior, AS_OF)
    assert _findings(report, "yield_fresh", "20Y")


def test_big_overnight_move_is_warning():
    prior, current = build_yield_curves()
    report = validate_yield_curve(current, prior, AS_OF)
    warning = _findings(report, "daily_move", "10Y")
    assert warning and warning[0].severity == "WARNING"


def test_clean_curve_passes():
    rows = [
        {"tenor": t, "yield_pct": 3.0 + i * 0.1,
         "as_of_date": AS_OF.isoformat(), "source": "Pricing Vendor"}
        for i, t in enumerate(EXPECTED_TENORS)
    ]
    report = validate_yield_curve(rows, rows, AS_OF)
    assert report.failed == 0
    assert report.warnings == 0


def test_yield_out_of_range_flagged():
    rows = [
        {"tenor": t, "yield_pct": 3.0,
         "as_of_date": AS_OF.isoformat(), "source": "Pricing Vendor"}
        for t in EXPECTED_TENORS
    ]
    rows[0]["yield_pct"] = 99.0
    report = validate_yield_curve(rows, rows, AS_OF)
    assert _findings(report, "yield_range", "1M")
