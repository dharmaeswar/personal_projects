"""Run the Comms Data Platform pipeline end to end.

Usage: python run_pipeline.py [--out DIR]
Default output directory is ./comms_tables (lake, catalog, reports).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from comms_platform.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="Run the comms data pipeline.")
    parser.add_argument("--out", default="comms_tables", help="output directory")
    args = parser.parse_args()
    results = run_pipeline(Path(args.out))
    print(json.dumps(results, indent=2, default=str))
    print(f"\nReports written to {args.out}/validation_report.txt")


if __name__ == "__main__":
    main()
