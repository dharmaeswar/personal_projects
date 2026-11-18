"""Plain-text validation report writer."""

from __future__ import annotations

from .checks import CheckResult


def render_report(
    results: list[CheckResult],
    bronze_rows: int,
    silver_rows: int,
    quarantine_rows: int,
    gold_groups: int,
    reconciliation: CheckResult,
) -> str:
    lines = [
        "LAKEHOUSE DATA QUALITY — VALIDATION REPORT",
        f"Bronze orders: {bronze_rows} rows",
        f"Silver orders: {silver_rows} rows",
        f"Quarantined rows: {quarantine_rows} rows",
        f"Gold daily groups: {gold_groups}",
        "",
        "BRONZE CHECKS",
    ]
    for r in results:
        lines.append(str(r))
    lines += [
        "",
        "RECONCILIATION",
        str(reconciliation),
        "",
        "SUMMARY",
    ]
    failed = [r for r in results if not r.passed]
    if failed:
        lines.append(
            f"{len(failed)} of {len(results)} bronze checks FAILED; "
            f"{quarantine_rows} bad rows quarantined, none dropped silently."
        )
    else:
        lines.append(f"All {len(results)} bronze checks passed.")
    lines.append(
        "Reconciliation: "
        + ("gold matches silver." if reconciliation.passed else "MISMATCH — see above.")
    )
    return "\n".join(lines) + "\n"
