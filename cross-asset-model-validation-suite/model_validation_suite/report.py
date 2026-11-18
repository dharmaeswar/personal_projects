"""Pass/fail summary reporting.

Emits a JSON summary (with full breach detail) and a flat CSV with one row
per check -- both are clean, stable schemas suitable for ingestion by a
dashboard tool such as Power BI.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .invariants.framework import CheckResult

CSV_COLUMNS = ["scenario_id", "asset_class", "invariant", "status",
               "measured", "limit", "detail"]


def summarise(results: list[CheckResult], config_name: str = "") -> dict:
    by_asset: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = by_asset.setdefault(r.asset_class, {"checks": 0, "passed": 0, "failed": 0})
        bucket["checks"] += 1
        bucket["passed" if r.passed else "failed"] += 1
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "config": config_name,
        "total_checks": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": (passed / total) if total else 0.0,
        "by_asset_class": by_asset,
        "breaches": [
            {
                "scenario_id": r.scenario_id,
                "asset_class": r.asset_class,
                "invariant": r.invariant,
                "measured": r.measured,
                "limit": r.limit,
                "detail": r.detail,
            }
            for r in results if not r.passed
        ],
    }


def write_json(results: list[CheckResult], path: str | Path, config_name: str = "") -> dict:
    summary = summarise(results, config_name=config_name)
    payload = dict(summary)
    payload["results"] = [
        {
            "scenario_id": r.scenario_id,
            "asset_class": r.asset_class,
            "invariant": r.invariant,
            "status": r.status,
            "measured": r.measured,
            "limit": r.limit,
            "detail": r.detail,
        }
        for r in results
    ]
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary


def write_csv(results: list[CheckResult], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for r in results:
            writer.writerow({
                "scenario_id": r.scenario_id,
                "asset_class": r.asset_class,
                "invariant": r.invariant,
                "status": r.status,
                "measured": f"{r.measured:.6e}",
                "limit": f"{r.limit:.6e}",
                "detail": r.detail,
            })
