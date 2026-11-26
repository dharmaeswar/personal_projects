"""Demo: market-data pipeline — ingest order events, featurize, train, gate.

Run: python3 run_market_data_demo.py
"""
import json
import sys

sys.path.insert(0, ".")

from ml_platform.market_data_pipeline import run_market_pipeline


def main():
    report = run_market_pipeline()
    print(f"events ingested: {report['n_events']}")
    print(f"feature rows: {report['n_rows']} "
          f"(train {report['n_train']}, test {report['n_test']})")
    print("candidate metrics:", json.dumps(report["candidate_metrics"]))
    print("baselines:", json.dumps(report["baselines"]))
    print("promotion gate:", json.dumps(report["gate"], indent=2))
    print("signal found (model AUC beats naive OFI rule):", report["signal_found"])
    print("manifest:", json.dumps(report["manifest"], indent=2))


if __name__ == "__main__":
    main()
