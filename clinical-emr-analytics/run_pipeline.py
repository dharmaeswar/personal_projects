"""Run the full clinical EMR analytics pipeline end to end.

Usage: python run_pipeline.py [--data data] [--out output]

Prints the run report summary and writes run_report.json,
dashboard.html, and dashboard_spec.json to the output directory.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from emr_analytics.lifecycle import run_pipeline


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data")
    parser.add_argument("--out", default="output")
    args = parser.parse_args()
    base = os.path.dirname(os.path.abspath(__file__))
    report = run_pipeline(os.path.join(base, args.data),
                          output_dir=os.path.join(base, args.out))
    print(json.dumps(report["measures"], indent=2))
    print("quarantined rows: %d" % report["measures"]["rows_quarantined"])
    for finding in report["findings"]:
        print("- %s / %s: %d rows (%.1f%%)"
              % (finding["feed"], finding["rule"], finding["count"],
                 finding["share_pct"]))
    print("phases: %s" % ", ".join(
        "%s=%s" % (p["phase"], p["status"]) for p in report["phases"]))


if __name__ == "__main__":
    main()
