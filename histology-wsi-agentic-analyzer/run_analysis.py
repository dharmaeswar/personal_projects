"""Run the agentic WSI study end to end and write outputs.

Usage: python run_analysis.py [--approve]
Without --approve the findings stay held for human review.
"""

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wsi_agent import agent, data, evaluate, report  # noqa: E402

QUESTION = "Does the treated arm differ from control on tile scores?"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approve", action="store_true",
                        help="human approval gate: release the findings")
    args = parser.parse_args()

    slides = data.make_study()
    result = agent.run_study(slides, QUESTION, approve=args.approve)
    n_treated = sum(1 for s in slides if s.label == "treated")
    n_control = len(slides) - n_treated

    outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "outputs")
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "protocol.txt"), "w") as fh:
        fh.write(report.protocol_text(QUESTION, n_treated, n_control,
                                      result["plan"]))
    with open(os.path.join(outdir, "report.txt"), "w") as fh:
        fh.write(report.report_text(QUESTION, result))
    with open(os.path.join(outdir, "per_slide.csv"), "w",
              newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["slide_id", "usable_tiles", "rejected_tiles",
                         "mean_score", "mean_nuclei"])
        for slide_id, s in sorted(result["summaries"].items()):
            writer.writerow([slide_id, s["usable_tiles"],
                             s["rejected_tiles"], s["mean_score"],
                             s["mean_nuclei"]])
    checks = evaluate.evaluate()
    print(f"Slides: {len(slides)} "
          f"(treated {n_treated}, control {n_control})")
    print(f"Comparison: {result['comparison']}")
    print(f"Claims kept: {len(result['kept_claims'])}, "
          f"rejected: {len(result['rejected_claims'])}")
    print(f"Release status: {result['status']}")
    print(f"Eval checks passed: {checks['passed']} "
          f"({checks['checks']})")
    print(f"Outputs written to {outdir}")


if __name__ == "__main__":
    main()
