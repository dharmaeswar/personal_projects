import json
from pathlib import Path

from src.run import run

PROJECT = Path(__file__).resolve().parent.parent
FEED = PROJECT / "data" / "sample_journals.json"


def test_end_to_end_sample_feed(tmp_path):
    report = run(FEED, tmp_path)
    assert report["feed_lines"] == 48
    assert report["quarantined_lines"] == 2  # unknown account + both-sides-set
    assert report["books_balanced"] is True
    assert report["trial_balance_total_debit"] == report["trial_balance_total_credit"]
    # Unbalanced journals: the planted one plus the two left one-sided by quarantine.
    assert {j["journal_id"] for j in report["unbalanced_journals"]} == {"J-3005", "J-3007", "J-3008"}
    # The re-posted J-1000 journal: both duplicate lines excluded.
    assert len(report["duplicate_lines"]) == 2
    # Planted anomalies: outlier, round-dollar, weekend and late postings (2 lines each).
    assert report["flagged_lines"] == 8
    # Outputs exist and agree with the report.
    assert (tmp_path / "trial_balance.csv").exists()
    assert (tmp_path / "anomaly_report.json").exists()
    close = json.loads((tmp_path / "close_report.json").read_text())
    assert close["books_balanced"] is True
    anomaly_report = json.loads((tmp_path / "anomaly_report.json").read_text())
    assert anomaly_report["flagged_lines"] == 8


def test_rerun_is_idempotent(tmp_path):
    first = run(FEED, tmp_path)
    second = run(FEED, tmp_path)
    assert first == second
