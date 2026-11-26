"""Run the evaluation harness: baseline vs improved regression report."""

import json

from research_platform.evaluate import regression_report


def main():
    report = regression_report()
    with open("research_eval_report.json", "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("Baseline :", report["baseline"]["summary"])
    print("Improved :", report["improved"]["summary"])
    print("Delta grounded rate:", report["delta_grounded_rate"])
    print("Delta citation coverage:", report["delta_citation_coverage"])
    print("Release gate passed:", report["release_gate_passed"])
    print("Report written to research_eval_report.json")


if __name__ == "__main__":
    main()
