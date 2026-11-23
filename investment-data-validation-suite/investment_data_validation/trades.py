"""Trade-data validations: dates, amounts, duplicates, referential integrity."""

from __future__ import annotations

from datetime import date, timedelta

from . import Finding, ValidationReport

REQUIRED_FIELDS = [
    "trade_id",
    "security_id",
    "trade_date",
    "settlement_date",
    "quantity",
    "price",
    "side",
    "counterparty",
]
MAX_SETTLEMENT_LAG_DAYS = 5


def _parse(d: str):
    try:
        return date.fromisoformat(d)
    except (TypeError, ValueError):
        return None


def validate_trades(
    rows: list[dict], valid_security_ids: set[str], as_of: date
) -> ValidationReport:
    findings: list[Finding] = []
    checks = passed = failed = 0

    def check(ok: bool, check_name: str, record_id: str, message: str) -> None:
        nonlocal checks, passed, failed
        checks += 1
        if ok:
            passed += 1
        else:
            failed += 1
            findings.append(
                Finding(check_name, "trades", record_id, "FAIL", message))

    seen_ids: set[str] = set()
    for row in rows:
        rid = str(row.get("trade_id") or "?")
        for f in REQUIRED_FIELDS:
            check(row.get(f) not in (None, ""), "required_fields", rid,
                  f"Missing or empty required field: {f}")
        if row.get("trade_id"):
            if rid in seen_ids:
                check(False, "unique_trade_id", rid,
                      "Duplicate trade_id in the feed")
            else:
                seen_ids.add(rid)
                check(True, "unique_trade_id", rid, "")
        check(row.get("security_id") in valid_security_ids,
              "security_exists", rid,
              f"Trade references security {row.get('security_id')!r}, "
              "which is not in the security master")
        trade_date = _parse(row.get("trade_date", ""))
        settle_date = _parse(row.get("settlement_date", ""))
        check(trade_date is not None and settle_date is not None
              and settle_date >= trade_date,
              "settlement_after_trade", rid,
              f"Settlement {row.get('settlement_date')} is before trade "
              f"{row.get('trade_date')}")
        if trade_date is not None and settle_date is not None:
            lag = (settle_date - trade_date).days
            check(0 <= lag <= MAX_SETTLEMENT_LAG_DAYS,
                  "settlement_lag", rid,
                  f"Settlement lag {lag} days exceeds "
                  f"{MAX_SETTLEMENT_LAG_DAYS}-day limit")
        check(trade_date is not None and trade_date <= as_of,
              "trade_not_future", rid,
              f"Trade date {row.get('trade_date')} is after {as_of}")
        qty = row.get("quantity")
        check(isinstance(qty, (int, float)) and qty > 0, "quantity_positive",
              rid, f"Quantity {qty} must be positive")
        price = row.get("price")
        check(isinstance(price, (int, float)) and price > 0, "price_positive",
              rid, f"Price {price} must be positive")
        check(row.get("side") in ("BUY", "SELL"), "side_valid", rid,
              f"Side {row.get('side')!r} must be BUY or SELL")
    return ValidationReport("trades", len(rows), checks, passed, failed,
                            findings)
