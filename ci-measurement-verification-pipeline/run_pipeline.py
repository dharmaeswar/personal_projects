#!/usr/bin/env python3
"""Run the seeded C&I M&V pipeline end to end.

Usage:
    python run_pipeline.py [--report report.json]

Stages the seeded meter readings, builds the 10-day baseline, computes
event performance and payments, runs the data-quality checks, and
writes the marts + report. Re-running with the same staged keys loads
0 new rows, demonstrating idempotent incremental loads.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mv_pipeline.baseline import build_baseline
from mv_pipeline.marts import mart_payments, mart_site_event_summary
from mv_pipeline.performance import event_performance, payment_for
from mv_pipeline.quality import run_quality_checks
from mv_pipeline.readings import EVENT_DATE, generate_readings
from mv_pipeline.staging import stage_readings

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="report.json")
    args = parser.parse_args()

    raw = generate_readings()
    staged, quarantine, stats = stage_readings(raw)
    # Second load of the same batch: idempotent, 0 new rows.
    _, _, restats = stage_readings(
        raw, existing_keys={(r["site_id"], r["timestamp"]) for r in staged})
    baseline = build_baseline(staged)
    performance = event_performance(baseline, staged)
    checks = run_quality_checks(staged, quarantine)
    report = {
        "event_date": str(EVENT_DATE.date()),
        "staging": stats,
        "reload_new_rows": restats["staged"],
        "performance": performance,
        "total_payment_usd": payment_for(performance),
        "quality": checks,
        "mart_site_event_summary": mart_site_event_summary(
            performance, EVENT_DATE),
        "mart_payments": mart_payments(performance, EVENT_DATE),
        "gaps_noted": ("Baseline is a 10-of-10 same-interval average; "
                       "no weather adjustment is applied."),
    }
    with open(os.path.join(HERE, args.report), "w") as fh:
        json.dump(report, fh, indent=2)

    print(f"staging: {stats['staged']}/{stats['raw']} staged, "
          f"{stats['duplicates']} duplicates, "
          f"{stats['quarantined']} quarantined, "
          f"{stats['late_arrivals']} late arrivals")
    print(f"reload of the same batch staged {restats['staged']} new rows")
    for site, p in sorted(performance.items()):
        print(f"{site}: baseline {p['baseline_kw']} kW, actual "
              f"{p['actual_kw']} kW, curtailed {p['curtailed_kw']} kW "
              f"({p['curtailed_kwh']} kWh), payment ${p['payment_usd']:.2f}")
    print(f"total payment: ${report['total_payment_usd']:.2f}")
    print(f"quality: gaps passed={checks['gaps']['passed']}, "
          f"late arrivals={checks['late_arrivals']['count']}, "
          f"quarantined={checks['quarantined']['count']}")
    print(f"report written to {args.report}")


if __name__ == "__main__":
    main()
