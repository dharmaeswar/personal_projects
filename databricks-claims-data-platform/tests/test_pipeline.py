"""Tests for the claims lakehouse pipeline: dedup, quality, gold, reconciliation."""
import pandas as pd
import pytest

from claims_platform.data import make_claims, make_members
from claims_platform.transforms import (
    aggregate_daily, aggregate_monthly, check_row, dedupe_latest,
    filter_valid, join_member_dim, reconcile, with_derived,
)


@pytest.fixture(scope="module")
def stages():
    raw = make_claims()
    members = make_members()
    deduped = dedupe_latest(raw)
    joined = join_member_dim(deduped, members)
    cleansed, quarantined = filter_valid(joined)
    cleansed = with_derived(cleansed)
    return {"raw": raw, "deduped": deduped, "cleansed": cleansed,
            "quarantined": quarantined, "members": members}


def test_raw_has_planted_defects(stages):
    assert len(stages["raw"]) == 324  # 300 clean + 24 planted defects


def test_dedup_keeps_latest_copy(stages):
    assert len(stages["deduped"]) == len(stages["raw"]) - 4
    assert stages["deduped"]["claim_id"].is_unique


def test_quarantine_counts_by_reason(stages):
    reasons = stages["quarantined"]["quarantine_reason"].value_counts().to_dict()
    # 4 late duplicate copies also fail: they carry paid_amount + $1.00, so the
    # kept copy breaks the paid = billed - adjustment rule (5 planted + 4 dup).
    assert reasons == {"null_member_id": 5, "negative_paid_amount": 4,
                       "unknown_diag_code": 3, "service_date_out_of_range": 3,
                       "paid_amount_mismatch": 9}
    assert len(stages["cleansed"]) == 296


def test_cleansed_passes_all_quality_rules(stages):
    c = stages["cleansed"]
    assert c["member_id"].notna().all()
    assert (c["paid_amount"] >= 0).all()
    assert c["diag_code"].isin({"I25", "M17", "C50", "Z00", "F32"}).all()
    assert ((c["paid_amount"] - (c["billed_amount"] - c["adjustment"])).abs() <= 0.01).all()
    assert c.apply(check_row, axis=1).isna().all()


def test_member_join_covers_every_claim(stages):
    assert stages["cleansed"]["plan"].notna().all()
    assert set(stages["cleansed"]["plan"]) <= {
        "Medicare Advantage", "Medicaid", "Commercial PPO", "Commercial HMO"}


def test_gold_daily_reconciles_to_silver(stages):
    gold = aggregate_daily(stages["cleansed"])
    ok, diff = reconcile(stages["cleansed"], gold)
    assert ok and diff == 0.0
    assert gold["total_paid"].sum() == pytest.approx(
        stages["cleansed"]["paid_amount"].sum(), abs=0.01)


def test_gold_monthly_covers_all_paid(stages):
    monthly = aggregate_monthly(stages["cleansed"])
    assert monthly["total_paid"].sum() == pytest.approx(
        stages["cleansed"]["paid_amount"].sum(), abs=0.01)
    assert monthly["claim_count"].sum() == 296


def test_paid_bands_assigned(stages):
    assert set(stages["cleansed"]["paid_band"]) <= {
        "low", "medium", "high", "very_high"}
    assert stages["cleansed"]["paid_band"].notna().all()


def test_members_seeded_and_stable():
    a, b = make_members(), make_members()
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 120
    assert a["member_id"].is_unique
