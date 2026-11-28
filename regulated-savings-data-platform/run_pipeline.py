"""Batch pipeline runner: ingest -> silver -> gold -> reconcile -> report.

Usage: python run_pipeline.py [--out tables] [--seed 42]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from savings_platform import ingest, pipeline, governance  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="tables")
    ap.add_argument("--seed", type=int, default=ingest.SEED)
    args = ap.parse_args()

    accounts = ingest.make_accounts(seed=args.seed)
    batch = ingest.make_contribution_batch(accounts, seed=args.seed)
    stream = ingest.make_stream_events(accounts, seed=args.seed)
    investments = ingest.make_investments(accounts, seed=args.seed)

    silver = pipeline.build_silver(accounts, batch, stream)
    history, closed = pipeline.scd2_status_history(accounts)
    gold = pipeline.build_gold(silver, investments)
    recon = governance.reconcile_balances(gold, silver)
    lineage = governance.build_lineage(silver)
    report = governance.run_report(silver, gold, recon)

    tables = {
        "accounts": silver["accounts"],
        "events_silver": silver["events"],
        "quarantine": silver["quarantine"],
        "account_status_history": history,
        "account_balances": gold["account_balances"],
        "monthly_contributions": gold["monthly_contributions"],
        "program_totals": gold["program_totals"],
        "lineage": lineage,
    }
    pipeline.write_tables(tables, args.out)
    governance.append_audit_log(args.out, [
        {"run": "batch-pipeline", "seed": args.seed,
         "raw_rows": report["raw_rows"],
         "silver_rows": report["silver_rows"],
         "quarantined_rows": report["quarantined_rows"],
         "status": report["status"]},
    ])
    with open("run_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
