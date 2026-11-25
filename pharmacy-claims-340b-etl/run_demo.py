"""End-to-end demo: full load, then an incremental load, then a re-run.

Expected output:
- Full load: 12 source claims -> 5 loaded, 7 quarantined, watermark 2026-11-23.
- Incremental load of claims_batch2.csv: 2 loaded (both dated 2026-11-24).
- Re-running the same batch: 0 loaded (watermark already past it).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claims_etl.loads import run_load

BASE = Path(__file__).resolve().parent
DB = BASE / "pharmacy_warehouse.sqlite"


def show(title, report):
    print(f"\n== {title} ==")
    for key in ("mode", "load_id", "source_rows", "loaded_rows",
                "quarantined_rows", "skipped_already_loaded",
                "watermark", "fact_rows", "reconciled"):
        print(f"  {key}: {report[key]}")
    for q in report["quarantine"]:
        print(f"  quarantined {q['claim_id']}: {'; '.join(q['violations'])}")


def main():
    if DB.exists():
        os.remove(DB)
    full = run_load(BASE / "data", DB, mode="full")
    show("FULL LOAD", full)
    inc = run_load(BASE / "data", DB, mode="incremental",
                   claims_file="claims_batch2.csv")
    show("INCREMENTAL LOAD (batch 2)", inc)
    rerun = run_load(BASE / "data", DB, mode="incremental",
                     claims_file="claims_batch2.csv")
    show("INCREMENTAL RE-RUN (same batch)", rerun)
    assert full["loaded_rows"] == 5 and full["quarantined_rows"] == 7
    assert full["reconciled"] and inc["loaded_rows"] == 2
    assert rerun["loaded_rows"] == 0 and rerun["reconciled"]
    print("\nDemo OK: loads reconcile; incremental re-run loads 0 rows.")


if __name__ == "__main__":
    main()
