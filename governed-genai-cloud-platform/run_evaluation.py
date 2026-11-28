"""Run the seeded evaluation suite and print the report.

Usage: python run_evaluation.py
"""

import json

from genai_platform import demo_knowledge_base, run_evaluation


def main() -> None:
    report = run_evaluation(demo_knowledge_base())
    printable = {k: v for k, v in report.items() if k != "results"}
    print(json.dumps(printable, indent=2))
    if report["failures"]:
        print("\nFailures:")
        for failure in report["failures"]:
            print(f"  - {failure['question']} (expected: {failure['expected']})")
    raise SystemExit(0 if report["pass_rate"] == 1.0 else 1)


if __name__ == "__main__":
    main()
