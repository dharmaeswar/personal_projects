"""Legacy-to-warehouse reconciliation for the investment data warehouse move.

Compares a legacy extract against the new investment data warehouse
snapshot on the same keys: row counts, key coverage, per-record values,
and aggregate market value within tolerance.
"""

from __future__ import annotations

from . import Finding, ValidationReport

VALUE_FIELDS = ["market_value", "price"]
AGG_TOLERANCE_PCT = 0.01


def reconcile_warehouse(
    legacy: list[dict], warehouse: list[dict]
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
                Finding(check_name, "warehouse_reconciliation", record_id,
                        "FAIL", message))

    check(len(legacy) == len(warehouse), "row_count_match", "ALL",
          f"Row counts differ: legacy {len(legacy)} vs warehouse "
          f"{len(warehouse)}")
    legacy_by_id = {r["security_id"]: r for r in legacy}
    wh_by_id = {r["security_id"]: r for r in warehouse}
    for sid in sorted(set(legacy_by_id) - set(wh_by_id)):
        check(False, "key_in_warehouse", sid,
              f"Security {sid} is in the legacy extract but missing from "
              "the warehouse")
    for sid in sorted(set(wh_by_id) - set(legacy_by_id)):
        check(False, "key_in_legacy", sid,
              f"Security {sid} is in the warehouse but has no legacy record")
    for sid in sorted(set(legacy_by_id) & set(wh_by_id)):
        for field_name in VALUE_FIELDS:
            old = legacy_by_id[sid].get(field_name)
            new = wh_by_id[sid].get(field_name)
            check(old == new, "value_match", sid,
                  f"{field_name} for {sid} differs: legacy {old} vs "
                  f"warehouse {new}")
    legacy_total = sum(r.get("market_value", 0) for r in legacy)
    wh_total = sum(r.get("market_value", 0) for r in warehouse)
    diff_pct = (
        abs(wh_total - legacy_total) / legacy_total * 100
        if legacy_total else 0.0
    )
    check(diff_pct <= AGG_TOLERANCE_PCT, "aggregate_market_value", "ALL",
          f"Total market value differs by {diff_pct:.2f}% "
          f"({legacy_total:,.2f} vs {wh_total:,.2f}), over the "
          f"{AGG_TOLERANCE_PCT}% tolerance")
    return ValidationReport(
        "warehouse_reconciliation", len(legacy), checks, passed, failed,
        findings)
