"""Streaming runner: consume the Kafka-style event log in micro-batches.

Usage: python run_streaming.py [--out tables]
Simulates Spark Structured Streaming: the event log is read in two
micro-batches, each deduped and validated the same way as the batch path,
and the running silver total is reported after each batch.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd  # noqa: E402

from savings_platform import ingest, pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tables")
    args = ap.parse_args()

    accounts = ingest.make_accounts()
    stream = ingest.make_stream_events(accounts)
    # Split the event log into two micro-batches by ingest order.
    half = len(stream) // 2
    batches = [stream.iloc[:half], stream.iloc[half:]]
    seen = pd.DataFrame()
    report = {"micro_batches": []}
    for i, micro in enumerate(batches, start=1):
        combined = pd.concat([seen, micro], ignore_index=True)
        deduped = pipeline.dedupe_latest(combined)
        clean, quar = pipeline.validate_contributions(
            deduped[deduped["event_type"].isin(
                ["contribution", "disbursement"])], accounts)
        seen = deduped
        report["micro_batches"].append({
            "batch": i,
            "events_in": int(len(micro)),
            "silver_rows_after": int(len(clean)),
            "quarantined_rows_after": int(len(quar)),
        })
    report["total_events"] = int(len(stream))
    report["final_silver_rows"] = int(report["micro_batches"][-1]["silver_rows_after"])
    with open("streaming_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
