"""Run the Enterprise Core Datasets pipeline end to end."""

from enterprise_core.run import run_pipeline

if __name__ == "__main__":
    wh, report = run_pipeline()
    print("checks passed:", report["checks_passed"])
