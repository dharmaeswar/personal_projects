"""Yield-curve validations: completeness, freshness, ranges, day-over-day moves."""

from __future__ import annotations

from datetime import date

from . import Finding, ValidationReport

EXPECTED_TENORS = ["1M", "3M", "6M", "1Y", "2Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
MIN_YIELD_PCT = -1.0
MAX_YIELD_PCT = 15.0
MAX_DAILY_MOVE_BP = 50.0


def validate_yield_curve(
    current: list[dict], prior: list[dict], as_of: date
) -> ValidationReport:
    findings: list[Finding] = []
    checks = passed = failed = 0

    def check(ok: bool, check_name: str, record_id: str, message: str,
              severity: str = "FAIL") -> None:
        nonlocal checks, passed, failed
        checks += 1
        if ok:
            passed += 1
        elif severity == "WARNING":
            findings.append(
                Finding(check_name, "yield_curve", record_id, severity,
                        message))
        else:
            failed += 1
            findings.append(
                Finding(check_name, "yield_curve", record_id, severity,
                        message))

    by_tenor: dict[str, dict] = {}
    for row in current:
        tenor = row.get("tenor", "?")
        if tenor in by_tenor:
            check(False, "unique_tenor", tenor,
                  f"Tenor {tenor} appears more than once in today's curve")
        else:
            by_tenor[tenor] = row
            check(True, "unique_tenor", tenor, "")
    for tenor in EXPECTED_TENORS:
        check(tenor in by_tenor, "tenor_present", tenor,
              f"Tenor {tenor} is missing from today's yield curve")
    prior_by_tenor = {r.get("tenor"): r for r in prior}
    for tenor, row in by_tenor.items():
        y = row.get("yield_pct")
        check(isinstance(y, (int, float)) and MIN_YIELD_PCT <= y <= MAX_YIELD_PCT,
              "yield_range", tenor,
              f"Yield {y}% for {tenor} is outside "
              f"{MIN_YIELD_PCT}% to {MAX_YIELD_PCT}%")
        check(row.get("as_of_date") == as_of.isoformat(), "yield_fresh", tenor,
              f"Yield for {tenor} is stamped {row.get('as_of_date')}, "
              f"not today's date {as_of}")
        prev = prior_by_tenor.get(tenor)
        if prev is not None and isinstance(y, (int, float)) \
                and isinstance(prev.get("yield_pct"), (int, float)):
            move_bp = abs(y - prev["yield_pct"]) * 100
            check(move_bp <= MAX_DAILY_MOVE_BP, "daily_move", tenor,
                  f"Yield for {tenor} moved {move_bp:.0f}bp overnight "
                  f"({prev['yield_pct']}% to {y}%), over the "
                  f"{MAX_DAILY_MOVE_BP:.0f}bp limit",
                  severity="WARNING")
    # Curve shape: flag an inversion (10Y below 2Y) as a warning, not a failure.
    two = by_tenor.get("2Y", {}).get("yield_pct")
    ten = by_tenor.get("10Y", {}).get("yield_pct")
    if isinstance(two, (int, float)) and isinstance(ten, (int, float)):
        check(ten >= two, "curve_not_inverted", "2Y-10Y",
              f"Curve is inverted: 10Y {ten}% is below 2Y {two}%",
              severity="WARNING")
    return ValidationReport("yield_curve", len(current), checks, passed,
                            failed, findings)
