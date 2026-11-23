"""Security-master validations: identifiers, completeness, dates, values."""

from __future__ import annotations

from datetime import date

from . import Finding, ValidationReport

REQUIRED_FIELDS = [
    "security_id",
    "cusip",
    "isin",
    "ticker",
    "issuer",
    "asset_class",
    "coupon_rate",
    "issue_date",
    "maturity_date",
    "face_value",
    "currency",
    "status",
]
ASSET_CLASSES = {"Corporate Bond", "Treasury", "MBS", "Municipal"}
CURRENCIES = {"USD", "EUR", "GBP"}

_CUSIP_VALUES = {str(i): i for i in range(10)}
_CUSIP_VALUES.update({chr(ord("A") + i): 10 + i for i in range(26)})
_CUSIP_VALUES.update({"*": 36, "@": 37, "#": 38})


def cusip_check_digit(body8: str) -> int:
    """Check digit for the first 8 characters of a CUSIP."""
    total = 0
    for i, ch in enumerate(body8):
        value = _CUSIP_VALUES[ch]
        if i % 2 == 1:  # 2nd, 4th, 6th, 8th positions are doubled
            value *= 2
        total += value // 10 + value % 10
    return (10 - total % 10) % 10


def valid_cusip(cusip: str) -> bool:
    if not isinstance(cusip, str) or len(cusip) != 9:
        return False
    if any(ch not in _CUSIP_VALUES for ch in cusip):
        return False
    return cusip_check_digit(cusip[:8]) == int(cusip[8])


def isin_check_digit(body11: str) -> int:
    """Luhn check digit for the first 11 characters of an ISIN."""
    digits = ""
    for ch in body11:
        if ch.isdigit():
            digits += ch
        else:
            digits += str(ord(ch) - ord("A") + 10)
    total = 0
    double = True
    for ch in reversed(digits):
        value = int(ch)
        if double:
            value *= 2
            if value > 9:
                value -= 9
        total += value
        double = not double
    return (10 - total % 10) % 10


def valid_isin(isin: str) -> bool:
    if not isinstance(isin, str) or len(isin) != 12:
        return False
    if not isin[:2].isalpha() or not isin[2:11].isalnum():
        return False
    if not isin[11].isdigit():
        return False
    return isin_check_digit(isin[:11]) == int(isin[11])


def _parse(d: str):
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError):
        return None


def validate_security_master(
    rows: list[dict], as_of: date
) -> ValidationReport:
    findings: list[Finding] = []
    checks = passed = failed = 0

    def check(ok: bool, check: str, record_id: str, message: str,
              severity: str = "FAIL") -> None:
        nonlocal checks, passed, failed
        checks += 1
        if ok:
            passed += 1
        elif severity == "WARNING":
            findings.append(Finding(check, "security_master", record_id,
                                    severity, message))
        else:
            failed += 1
            findings.append(Finding(check, "security_master", record_id,
                                    severity, message))

    seen_ids: dict[str, str] = {}
    seen_cusips: dict[str, str] = {}
    for row in rows:
        rid = str(row.get("security_id") or "?")
        for f in REQUIRED_FIELDS:
            check(row.get(f) not in (None, ""), "required_fields", rid,
                  f"Missing or empty required field: {f}")
        if row.get("security_id"):
            if rid in seen_ids:
                check(False, "unique_security_id", rid,
                      f"Duplicate security_id, first seen as {seen_ids[rid]}")
            else:
                seen_ids[rid] = rid
                check(True, "unique_security_id", rid, "")
        cusip = row.get("cusip", "")
        check(valid_cusip(cusip), "valid_cusip", rid,
              f"CUSIP {cusip!r} fails the check-digit test")
        if cusip:
            if cusip in seen_cusips:
                check(False, "unique_cusip", rid,
                      f"CUSIP {cusip} already used by {seen_cusips[cusip]}")
            else:
                seen_cusips[cusip] = rid
                check(True, "unique_cusip", rid, "")
        check(valid_isin(row.get("isin", "")), "valid_isin", rid,
              f"ISIN {row.get('isin')!r} fails the check-digit test")
        coupon = row.get("coupon_rate")
        check(isinstance(coupon, (int, float)) and 0 <= coupon <= 20,
              "coupon_range", rid,
              f"Coupon {coupon} outside 0-20% for a fixed income security")
        face = row.get("face_value")
        check(isinstance(face, (int, float)) and face > 0, "face_value", rid,
              f"Face value {face} must be positive")
        check(row.get("asset_class") in ASSET_CLASSES, "asset_class", rid,
              f"Unknown asset class {row.get('asset_class')!r}")
        check(row.get("currency") in CURRENCIES, "currency", rid,
              f"Unknown currency {row.get('currency')!r}")
        issue = _parse(row.get("issue_date", ""))
        maturity = _parse(row.get("maturity_date", ""))
        check(issue is not None and maturity is not None
              and maturity > issue, "maturity_after_issue", rid,
              f"Maturity {row.get('maturity_date')} is not after issue "
              f"{row.get('issue_date')}")
        if maturity is not None:
            expected = "Matured" if maturity <= as_of else "Active"
            check(row.get("status") == expected, "status_consistent", rid,
                  f"Status {row.get('status')!r} but maturity {maturity} "
                  f"implies {expected!r} as of {as_of}",
                  severity="WARNING")
    return ValidationReport("security_master", len(rows), checks, passed,
                            failed, findings)
