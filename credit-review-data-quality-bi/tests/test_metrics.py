from credit_review_bi import build_dataset, build_dashboard, run_quality_checks
from credit_review_bi.metrics import format_dashboard


def test_dashboard_counts_match_source_tables():
    ds = build_dataset()
    checks = run_quality_checks(ds)
    dash = build_dashboard(ds, checks)
    assert dash["portfolio"]["loan_count"] == len(ds.loans)
    assert dash["reviews"]["review_count"] == len(ds.reviews)
    assert dash["findings"]["finding_count"] == len(ds.findings)
    open_count = sum(1 for f in ds.findings if f["status"] in ("Open", "Overdue"))
    assert dash["findings"]["open_findings"] == open_count


def test_dashboard_totals_are_sane():
    ds = build_dataset()
    dash = build_dashboard(ds, run_quality_checks(ds))
    assert dash["portfolio"]["total_outstanding_usd"] > 0
    assert dash["reviews"]["median_cycle_days"] is not None
    assert 5 <= dash["reviews"]["median_cycle_days"] <= 60
    assert sum(dash["portfolio"]["loans_by_risk_rating"].values()) == 121  # one loan has no rating
    assert dash["data_quality"]["checks_run"] == 9
    assert dash["data_quality"]["score"] < 1.0  # planted defects fail checks


def test_findings_by_severity_sums_to_open():
    ds = build_dataset()
    dash = build_dashboard(ds)
    by_sev = dash["findings"]["open_findings_by_severity"]
    assert sum(by_sev.values()) == dash["findings"]["open_findings"]
    assert set(by_sev) <= {"Low", "Moderate", "High", "Critical"}


def test_dashboard_without_checks_has_no_quality_section():
    ds = build_dataset()
    dash = build_dashboard(ds)
    assert "data_quality" not in dash


def test_format_dashboard_is_plain_text():
    ds = build_dataset()
    text = format_dashboard(build_dashboard(ds, run_quality_checks(ds)))
    assert "CREDIT REVIEW" in text
    assert "FAILED" in text  # planted defects surface in the report
    assert "Data quality" in text
