#!/usr/bin/env python3
"""Run the agentic analytics pipeline and print the validation report."""

import sys

from agentic_stats.pipeline import render_report, run_pipeline


def main():
    report = run_pipeline()
    text = render_report(report)
    print(text)
    with open("evaluation_report.txt", "w") as fh:
        fh.write(text)
    # The report itself records which claims failed validation; the run
    # succeeds whenever the pipeline completes (failed claims are findings,
    # not errors), so the exit code stays 0.
    return 0


if __name__ == "__main__":
    sys.exit(main())
