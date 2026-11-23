#!/usr/bin/env python3
"""CLI: run the Global Logistics Exports ETL pipeline.

Usage:
    python run_pipeline.py --manifest data/sample_manifests.csv \
        --rates data/fx_rates.csv --db exports.db
"""

import argparse
import json

from exports_etl import pipeline


def main():
    parser = argparse.ArgumentParser(description="Global Logistics Exports ETL")
    parser.add_argument("--manifest", required=True, help="Export manifest CSV")
    parser.add_argument("--rates", required=True, help="FX rates CSV")
    parser.add_argument("--db", required=True, help="SQLite warehouse path")
    args = parser.parse_args()
    report = pipeline.run(args.manifest, args.rates, args.db)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
