"""End-to-end run: generate -> bronze -> silver -> gold -> CAT -> tuning.

Writes everything under ``out/`` next to this file (lakehouse tables)
and prints a short summary. Run from the project root:

    .venv/bin/python run_pipeline.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from surveillance_lakehouse import cat as cat_mod
from surveillance_lakehouse import generate as gen
from surveillance_lakehouse import gold as gold_mod
from surveillance_lakehouse import ingest as ingest_mod
from surveillance_lakehouse import model as model_mod
from surveillance_lakehouse import snapshots as snap
from surveillance_lakehouse import tuning as tuning_mod

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
BRONZE = OUT / "bronze"
SILVER = OUT / "silver"
GOLD = OUT / "gold"


def main() -> dict:
    feeds = gen.generate()
    summary: dict = {}

    # Bronze
    bronze_report = {}
    for name, df in feeds.items():
        result = ingest_mod.ingest(name, df, BRONZE)
        snap.record_snapshot(BRONZE / name, "append",
                             result["rows_written"])
        bronze_report[name] = result
    summary["bronze"] = bronze_report

    # Silver
    silver_report = model_mod.build_silver(BRONZE, SILVER)
    for name in ("dim_instrument", "dim_account", "fact_order",
                 "fact_execution", "fact_trade"):
        rows = pd.read_parquet(SILVER / f"{name}.parquet")
        snap.record_snapshot(SILVER / name, "overwrite", len(rows))
    summary["silver"] = silver_report

    # Partitioned copy of fact_trade for the tuning comparison.
    tuning_mod.write_partitioned_trades(SILVER)

    # Gold
    dq = gold_mod.build_gold(SILVER, GOLD)
    for name in ("account_day_features", "cat_events"):
        rows = pd.read_parquet(GOLD / f"{name}.parquet")
        snap.record_snapshot(GOLD / name, "overwrite", len(rows))
    summary["gold_dq"] = dq

    # CAT export + tuning
    summary["cat"] = cat_mod.export_cat(GOLD, OUT / "cat_report.txt")
    summary["tuning"] = tuning_mod.tune(SILVER, OUT / "tuning_report.md")

    (OUT / "run_summary.json").write_text(json.dumps(summary, indent=2,
                                                     default=str))
    print(f"Bronze: orders {bronze_report['orders']['rows_written']} rows, "
          f"{bronze_report['orders']['rows_quarantined']} quarantined; "
          f"executions {bronze_report['executions']['rows_written']}; "
          f"trades {bronze_report['trades']['rows_written']}")
    print(f"Silver: {silver_report['fact_rows']}; "
          f"duplicates removed {silver_report['duplicates_removed']}")
    print(f"Gold: wash candidates {dq['wash_candidates']} "
          f"({dq['wash_candidate_accounts']}); reconciliation "
          f"matches={dq['reconciliation']['matches']}")
    print(f"CAT: {summary['cat']['rows']} rows -> {summary['cat']['path']}")
    print(f"Tuning: partitioned {summary['tuning']['partitioned_ms']} ms "
          f"vs full scan {summary['tuning']['full_scan_ms']} ms "
          f"({summary['tuning']['speedup']}x)")
    return summary


if __name__ == "__main__":
    main()
