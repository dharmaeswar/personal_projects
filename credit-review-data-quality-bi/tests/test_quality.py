from credit_review_bi import build_dataset, run_quality_checks
from credit_review_bi.quality import (
    quality_score, lineage_for, definition_for, BUSINESS_DEFINITIONS)


def test_checks_catch_the_planted_defects():
    ds = build_dataset()
    checks = run_quality_checks(ds)
    by_name = {c.name: c for c in checks}
    assert by_name["uniqueness: loan_id"].passed is False
    assert "LN-0001" in by_name["uniqueness: loan_id"].failed_ids
    assert by_name["validity: outstanding >= 0"].passed is False
    assert "LN-9999" in by_name["validity: outstanding >= 0"].failed_ids
    assert by_name["completeness: risk_rating present"].passed is False
    assert "LN-9999" in by_name["completeness: risk_rating present"].failed_ids
    orphan = by_name["referential integrity: finding.review_id exists"]
    assert orphan.passed is False
    assert "FD-9999" in orphan.failed_ids


def test_clean_dataset_passes_all_checks():
    ds = build_dataset()
    ds.loans = [r for r in ds.loans if r["loan_id"] not in ("LN-9999",)]
    ds.loans = [r for i, r in enumerate(ds.loans)
                if not (r["loan_id"] == "LN-0001" and i > 0)]
    ds.findings = [f for f in ds.findings if f["finding_id"] != "FD-9999"]
    checks = run_quality_checks(ds)
    assert all(c.passed for c in checks), [c.name for c in checks if not c.passed]


def test_quality_score_is_a_share():
    ds = build_dataset()
    checks = run_quality_checks(ds)
    score = quality_score(checks)
    assert 0.0 < score < 1.0  # planted defects fail some checks
    assert quality_score([]) == 0.0
    assert quality_score([c for c in checks if c.passed]) == 1.0


def test_lineage_and_definitions_cover_dashboard_metrics():
    assert lineage_for("data_quality_score") == ["loans", "reviews", "findings"]
    assert lineage_for("open_findings_by_severity") == ["findings"]
    assert lineage_for("unknown_metric") == []
    for field in ("loan_id", "outstanding", "risk_rating", "severity"):
        assert definition_for(field) is not None
        assert field in BUSINESS_DEFINITIONS
    assert definition_for("not_a_field") is None


def test_check_result_carries_failed_row_ids():
    ds = build_dataset()
    checks = run_quality_checks(ds)
    failing = [c for c in checks if not c.passed]
    assert failing
    for check in failing:
        assert check.failed_ids
        assert "rows failed" in check.detail
