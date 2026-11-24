"""Run the seeded evaluation set and print the metrics report.

Usage: python run_evaluation.py
Writes evaluation_report.txt next to this file. Exit code 0 when every
case passes and every answer is grounded, 1 otherwise.
"""

import sys

from bank_rag.evaluate import format_evaluation_report, run_evaluation

if __name__ == "__main__":
    evaluation = run_evaluation()
    report = format_evaluation_report(evaluation)
    print(report)
    with open("evaluation_report.txt", "w") as handle:
        handle.write(report + "\n")
    sys.exit(0 if evaluation["accuracy"] == 1.0
             and evaluation["groundedness"] == 1.0 else 1)
