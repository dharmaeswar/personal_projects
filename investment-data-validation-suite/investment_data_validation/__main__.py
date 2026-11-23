"""Run every investment-data validation and assemble one combined report."""

from __future__ import annotations

import json
from datetime import date

from . import ValidationReport
from .data import (
    AS_OF,
    build_security_master,
    build_trades,
    build_warehouse_snapshots,
    build_yield_curves,
)
from .security_master import validate_security_master
from .trades import validate_trades
from .warehouse import reconcile_warehouse
from .yields import validate_yield_curve


def run_all(as_of: date = AS_OF) -> dict[str, ValidationReport]:
    securities = build_security_master()
    trades = build_trades(securities)
    prior_curve, current_curve = build_yield_curves()
    legacy, warehouse = build_warehouse_snapshots(securities)
    return {
        "security_master": validate_security_master(securities, as_of),
        "trades": validate_trades(
            trades, {s["security_id"] for s in securities}, as_of),
        "yield_curve": validate_yield_curve(current_curve, prior_curve, as_of),
        "warehouse_reconciliation": reconcile_warehouse(legacy, warehouse),
    }


def summarize(reports: dict[str, ValidationReport]) -> dict:
    total_checks = sum(r.checks_run for r in reports.values())
    total_failed = sum(r.failed for r in reports.values())
    total_warnings = sum(r.warnings for r in reports.values())
    return {
        "as_of": AS_OF.isoformat(),
        "overall_pass": total_failed == 0,
        "total_checks": total_checks,
        "total_failed": total_failed,
        "total_warnings": total_warnings,
        "datasets": {name: r.to_dict() for name, r in reports.items()},
    }


def main() -> None:
    reports = run_all()
    summary = summarize(reports)
    for name, report in reports.items():
        status = "CLEAN" if report.is_clean else f"{report.failed} FAILURES"
        print(f"{name}: {report.records_checked} records, "
              f"{report.checks_run} checks, {report.passed} passed, "
              f"{status}, {report.warnings} warnings")
        for f in report.findings:
            print(f"  [{f.severity}] {f.check} {f.record_id}: {f.message}")
    print(f"OVERALL: {summary['total_checks']} checks, "
          f"{summary['total_failed']} failures, "
          f"{summary['total_warnings']} warnings")
    with open("validation_report.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    print("Wrote validation_report.json")


if __name__ == "__main__":
    main()
