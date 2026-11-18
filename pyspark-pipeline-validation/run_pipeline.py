"""Run the batch pipeline and write Parquet tables + validation report."""
from pathlib import Path

from spark_pipeline.pipeline import run_pipeline
from spark_pipeline.report import render_report

ROOT = Path(__file__).resolve().parent


def main():
    summary, checks, invalid = run_pipeline(ROOT)
    (ROOT / "validation_report.txt").write_text(render_report(summary, checks, invalid))
    print(f"raw={summary['raw_rows']} duplicates={summary['duplicates_removed']} "
          f"quarantined={summary['quarantined_rows']} cleansed={summary['cleansed_rows']} "
          f"gold={summary['gold_rows']} partitions={summary['partitions']}")
    print(f"checks: {summary['checks_passed']}/{summary['checks_total']} passed, "
          f"reconciliation={'PASS' if summary['reconciliation_passed'] else 'FAIL'}")


if __name__ == "__main__":
    main()
