"""Run the risk-technology ETL and write Parquet tables + validation report."""
from pathlib import Path

from spark_pipeline.risk_pipeline import render_risk_report, run_risk_pipeline

ROOT = Path(__file__).resolve().parent


def main():
    summary, findings, invalid = run_risk_pipeline(ROOT)
    (ROOT / "risk_validation_report.txt").write_text(
        render_risk_report(summary, findings, invalid)
    )
    print(f"raw={summary['raw_rows']} duplicates={summary['duplicates_removed']} "
          f"quarantined={summary['quarantined_rows']} cleansed={summary['cleansed_rows']} "
          f"gold={summary['gold_rows']} partitions={summary['partitions']}")
    print(f"triage: {summary['triage']}, "
          f"reconciliation={'PASS' if summary['reconciliation_passed'] else 'FAIL'}")


if __name__ == "__main__":
    main()
