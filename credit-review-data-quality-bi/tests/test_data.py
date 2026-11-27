from credit_review_bi import build_dataset


def test_dataset_is_deterministic():
    a, b = build_dataset(), build_dataset()
    assert a.loans == b.loans
    assert a.reviews == b.reviews
    assert a.findings == b.findings


def test_dataset_has_three_tables():
    ds = build_dataset()
    assert len(ds.loans) == 122  # 120 generated + 2 planted
    assert len(ds.reviews) > 90
    assert len(ds.findings) > 50


def test_planted_defects_present():
    ds = build_dataset()
    dup = [r for r in ds.loans if r["loan_id"] == "LN-0001"]
    assert len(dup) == 2
    bad = [r for r in ds.loans if r["loan_id"] == "LN-9999"][0]
    assert bad["outstanding"] < 0
    assert bad["risk_rating"] is None
    orphan = [f for f in ds.findings if f["finding_id"] == "FD-9999"][0]
    assert orphan["review_id"] == "RV-9999"


def test_loan_fields_cover_governed_columns():
    ds = build_dataset()
    for loan in ds.loans:
        assert {"loan_id", "segment", "outstanding", "risk_rating",
                "review_due", "status"} <= set(loan)
