"""Run the monthly payer file exchange + HEDIS pipeline.

Usage:
    python run_pipeline.py [--month YYYY-MM] [--workdir DIR]

Defaults: month 2026-10, workdir ./work (created if missing).
Writes hedis_report.json / hedis_report.txt, the Power BI semantic
model, and the Fabric Warehouse SQLite stand-in under the workdir.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fabric_hedis.pipeline import run_monthly


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", default="2026-10")
    parser.add_argument("--workdir", default=str(
        Path(__file__).resolve().parent / "work"))
    args = parser.parse_args()
    summary = run_monthly(args.workdir, args.month)
    print("month: %s" % summary["month"])
    print("bronze claims: %d (duplicates removed: %d)"
          % (summary["silver"]["bronze_claims"],
             summary["silver"]["duplicates_removed"]))
    print("silver claims: %d; quarantined: %d"
          % (summary["silver"]["silver_claims"],
             summary["silver"]["quarantined"]))
    for row in summary["hedis"]:
        print("%s: %d/%d = %.1f%%" % (row["measure"], row["numerator"],
                                      row["denominator"], row["rate"] * 100))
    print("vendor round-trip: %d accepted, %d rejected"
          % (summary["vendor"]["accepted"], summary["vendor"]["rejected"]))
    print(summary["health"])


if __name__ == "__main__":
    main()
