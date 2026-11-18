"""Run the AI evaluation data-quality pipeline on the synthetic corpus.

Writes quality_report.json and quality_report.txt next to this script and
prints the gate result. Exits 1 when the gate fails (critical findings),
so it can be wired into a CI or pipeline step.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from eval_quality.checks import run_all_checks
from eval_quality.report import render_json, render_text
from eval_quality.samples import build_corpus


def main():
    records = build_corpus()
    report = run_all_checks(records)
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "quality_report.json"), "w") as fh:
        fh.write(render_json(report))
    with open(os.path.join(here, "quality_report.txt"), "w") as fh:
        fh.write(render_text(report))
    print(render_text(report))
    return 0 if report["summary"]["gate"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
