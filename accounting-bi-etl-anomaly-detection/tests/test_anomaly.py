from conftest import make_line
from src import anomaly


def _lines_for_account(amounts, account="6000"):
    return [
        make_line(entry_id=f"E-{i:04d}", account=account, debit=a, credit=0)
        for i, a in enumerate(amounts)
    ]


def test_outlier_flagged_and_normal_lines_not():
    lines = _lines_for_account([8000, 9000, 10000, 11000, 12000, 9500, 10500, 250000])
    flagged = anomaly.detect_outliers(lines)
    assert list(flagged) == ["E-0007"]
    assert "250,000" in flagged["E-0007"]


def test_outlier_skipped_when_too_few_lines():
    assert anomaly.detect_outliers(_lines_for_account([100, 200, 300, 999999])) == {}


def test_round_dollar_flagged():
    lines = [make_line(entry_id="E-1", debit=50000), make_line(entry_id="E-2", debit=49999)]
    flagged = anomaly.detect_round_numbers(lines)
    assert list(flagged) == ["E-1"]


def test_small_round_amounts_not_flagged():
    assert anomaly.detect_round_numbers([make_line(debit=1000)]) == {}


def test_weekend_posting_flagged():
    # 2026-10-17 is a Saturday; 2026-10-19 is a Monday.
    lines = [
        make_line(entry_id="E-1", posting_date="2026-10-17"),
        make_line(entry_id="E-2", posting_date="2026-10-19"),
    ]
    flagged = anomaly.detect_weekend_postings(lines)
    assert list(flagged) == ["E-1"]


def test_late_posting_into_closed_period_flagged():
    lines = [
        make_line(entry_id="E-1", posting_date="2026-08-28", fiscal_period="2026-08"),
        make_line(entry_id="E-2", posting_date="2026-10-05", fiscal_period="2026-10"),
    ]
    flagged = anomaly.detect_late_postings(lines)
    assert list(flagged) == ["E-1"]


def test_benford_distribution_sums_to_one():
    lines = _lines_for_account([1234, 2345, 3456, 4567, 5678, 6789, 7890, 8912, 9123, 10234])
    dist, max_dev = anomaly.benford_check(lines)
    assert abs(sum(v[0] for v in dist.values()) - 1.0) < 0.001
    assert 0 <= max_dev <= 1


def test_run_all_checks_merges_flags():
    lines = [make_line(entry_id="E-1", posting_date="2026-10-17", debit=50000)]
    merged = anomaly.run_all_checks(lines)
    assert len(merged["E-1"]) == 2  # weekend + round-dollar
