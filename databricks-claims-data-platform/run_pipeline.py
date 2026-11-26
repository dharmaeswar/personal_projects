"""Run the claims pipeline end to end, then print the validation summary."""
from claims_platform.pipeline import run

if __name__ == "__main__":
    summary, checks = run()
    print(f"raw={summary['raw']} duplicates={summary['duplicates_removed']} "
          f"quarantined={summary['quarantined']} cleansed={summary['cleansed']} "
          f"gold_daily={summary['gold_daily_rows']} total_paid=${summary['total_paid']:,.2f}")
    print(f"checks: {summary['checks_passed']} passed, "
          f"reconciliation={'PASS' if checks['reconciliation'] else 'FAIL'}")
