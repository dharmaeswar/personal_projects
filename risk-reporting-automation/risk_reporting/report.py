"""Report rendering: text report plus Excel-friendly CSV outputs."""

from __future__ import annotations

import csv
from pathlib import Path

from .data import AS_OF_DATE
from .limits import LimitResult
from .stress import StressResult


def render_report(as_of_date: str, limit_results: list[LimitResult],
                  stress_results: list[StressResult],
                  exceptions: list[dict], reconciliation: list[str]) -> str:
    n_breach = sum(1 for r in limit_results if r.status == "BREACH")
    n_warn = sum(1 for r in limit_results if r.status == "WARNING")
    lines = [
        "RISK REPORTING — LIMITS & LIQUIDITY STRESS",
        f"As of: {as_of_date}   (synthetic data — not real positions)",
        "=" * 60,
        "",
        "LIMIT UTILISATION BY DESK AND RISK TYPE",
        f"{'Desk':<22}{'Risk type':<16}{'Exposure':>14}{'Limit':>14}"
        f"{'Util %':>9}  Status",
    ]
    for r in limit_results:
        lines.append(
            f"{r.desk:<22}{r.risk_type:<16}{r.exposure_usd:>14,.2f}"
            f"{r.limit_usd:>14,.2f}{r.utilisation * 100:>8.1f}%  {r.status}"
        )
    lines += [
        "",
        f"Limits checked: {len(limit_results)}  "
        f"Breaches: {n_breach}  Warnings: {n_warn}",
        "",
        "LIQUIDITY STRESS — COVERAGE RATIO",
        f"{'Scenario':<12}{'Liquid assets':>16}{'Stressed outflows':>20}"
        f"{'Coverage':>11}  Status",
    ]
    for s in stress_results:
        lines.append(
            f"{s.scenario:<12}{s.liquid_assets:>16,.2f}{s.stressed_outflows:>20,.2f}"
            f"{s.coverage_ratio:>11.2f}  {s.status}"
        )
    lines += [
        "",
        "EXCEPTIONS",
        f"Exception queue: {len(exceptions)} item(s)",
    ]
    for e in exceptions:
        lines.append(
            f"  [{e['severity']}] {e['trade_id']} {e['desk']}/{e['risk_type']}: "
            f"{e['reason']}"
        )
    lines += [
        "",
        "RECONCILIATION (Python aggregates vs SQL aggregates)",
        "PASS — no mismatches" if not reconciliation
        else "FAIL — " + "; ".join(reconciliation),
        "",
        "Sign-off: see signoff_checklist.csv — breaches and exceptions "
        "must be reviewed before this report is distributed.",
    ]
    return "\n".join(lines) + "\n"


def write_csv(path: str | Path, header: list[str], rows: list[list]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def write_outputs(out_dir: str | Path, limit_results: list[LimitResult],
                  stress_results: list[StressResult],
                  exceptions: list[dict]) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    paths["breaches"] = out / "limit_breaches.csv"
    write_csv(
        paths["breaches"],
        ["desk", "risk_type", "exposure_usd", "limit_usd",
         "utilisation", "status"],
        [[r.desk, r.risk_type, r.exposure_usd, r.limit_usd,
          r.utilisation, r.status] for r in limit_results],
    )
    paths["stress"] = out / "stress_results.csv"
    write_csv(
        paths["stress"],
        ["scenario", "liquid_assets_bn", "stressed_outflows_bn",
         "coverage_ratio", "status"],
        [[s.scenario, s.liquid_assets, s.stressed_outflows,
          s.coverage_ratio, s.status] for s in stress_results],
    )
    paths["exceptions"] = out / "exceptions.csv"
    write_csv(
        paths["exceptions"],
        ["trade_id", "desk", "risk_type", "reason", "severity"],
        [[e["trade_id"], e["desk"], e["risk_type"], e["reason"],
          e["severity"]] for e in exceptions],
    )
    return paths
