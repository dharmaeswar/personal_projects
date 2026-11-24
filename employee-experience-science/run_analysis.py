"""Run the full employee-experience analysis and write the report."""

from experience_science.data import generate
from experience_science.defects import find_defects
from experience_science.feedback import benchmark
from experience_science.forecast import workforce_plan
from experience_science.report import build_report


def main():
    rows = generate()
    defects, corrected_alpha = find_defects(rows)
    fb_bench = benchmark(rows)
    plan = workforce_plan(rows)
    report = build_report(rows, defects, corrected_alpha, fb_bench, plan)
    with open("experience_report.txt", "w") as f:
        f.write(report)
    print(report)


if __name__ == "__main__":
    main()
