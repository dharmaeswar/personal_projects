"""Run the seeded eval suite and print the pass/fail summary."""

from quality_platform.evaluate import run_evals
from quality_platform.pipeline import build_system

if __name__ == "__main__":
    _, _, client = build_system()
    summary = run_evals(client)
    for case in summary["cases"]:
        mark = "PASS" if case["passed"] else "FAIL"
        print(f"[{mark}] judge {case['judge_mean']}: {case['question']}")
        if case["missing_facts"]:
            print(f"       missing facts: {case['missing_facts']}")
        if case["reasons"]:
            print(f"       reasons: {case['reasons']}")
    print(f"{summary['passed']}/{summary['total']} eval cases passed "
          f"(pass rate {summary['pass_rate']})")
