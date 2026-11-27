"""Render the human-readable validation report."""

from __future__ import annotations

from .checks import CheckResult
from .monitoring import PipelineMetrics
from .privacy import privacy_summary_lines


def render_report(
    results: list[CheckResult],
    bronze_rows: int,
    silver_rows: int,
    quarantine_rows: int,
    late_rows: int,
    gold_groups: int,
    reconciliation: CheckResult,
    metrics: PipelineMetrics,
    silver_spend: float,
    gold_spend: float,
    privacy_rollup: dict | None = None,
) -> str:
    failed = [r for r in results if not r.passed]
    lines = [
        "Advertising ETL Pipeline — Validation Report",
        "=" * 48,
        "",
        f"Bronze events: {bronze_rows} rows",
        f"Silver events: {silver_rows} rows",
        f"Quarantined rows: {quarantine_rows} rows",
        f"Late-arriving rows in silver: {late_rows} rows",
        f"Gold daily campaign groups: {gold_groups}",
        f"Silver total spend: ${silver_spend:,.2f}",
        f"Gold total spend:   ${gold_spend:,.2f}",
        "",
        "Bronze checks "
        f"({len(results) - len(failed)} of {len(results)} passed, "
        f"{len(failed)} FAILED):",
    ]
    for r in results:
        lines.append(f"  {r}")
    lines += [
        "",
        f"Reconciliation: {reconciliation}",
        "",
    ]
    lines += metrics.summary_lines()
    if privacy_rollup is not None:
        lines += [""]
        lines += privacy_summary_lines(privacy_rollup)
    lines += [
        "",
        "Lineage: every silver row maps to its bronze event_id, and every "
        "gold group lists the silver event_ids that fed it "
        "(see lineage.json).",
        "All data is synthetic and seeded; no real advertiser data is used.",
    ]
    return "\n".join(lines) + "\n"
