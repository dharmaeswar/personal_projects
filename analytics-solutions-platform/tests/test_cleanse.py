import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics_solutions.cleanse import (cleanse_policy_rows, dedupe_by_key,
                                          engineer_activity_features, engineer_policy_features,
                                          premium_band)

AS_OF = date(2026, 11, 20)


def _row(**kw):
    base = {"policy_id": "P1", "holder_id": "H1", "advisor_id": "A1",
            "product": "term_life", "premium_annual": "1200",
            "effective_date": "2022-01-01", "status": "active"}
    base.update(kw)
    return base


def test_cleanse_quarantines_missing_id_bad_premium_bad_date():
    clean, quarantined = cleanse_policy_rows([
        _row(), _row(policy_id=""), _row(policy_id="P2", premium_annual="abc"),
        _row(policy_id="P3", premium_annual="-5"), _row(policy_id="P4", effective_date="junk"),
    ])
    assert len(clean) == 1
    assert len(quarantined) == 4
    reasons = sorted(q["_quarantine_reason"] for q in quarantined)
    assert reasons == ["bad effective_date", "bad premium_annual", "bad premium_annual", "missing policy_id"]
    assert isinstance(clean[0]["premium_annual"], float)
    assert isinstance(clean[0]["effective_date"], date)


def test_dedupe_keeps_first_reports_rest():
    kept, dupes = dedupe_by_key([{"policy_id": "P1"}, {"policy_id": "P1"}, {"policy_id": "P2"}], "policy_id")
    assert len(kept) == 2 and len(dupes) == 1


def test_premium_band_boundaries():
    assert premium_band(999) == "under_1k"
    assert premium_band(1_000) == "1k_5k"
    assert premium_band(5_000) == "5k_25k"
    assert premium_band(25_000) == "25k_plus"


def test_engineer_policy_features_tenure_and_band():
    clean, _ = cleanse_policy_rows([_row(effective_date="2021-11-20", premium_annual="3000")])
    feats = engineer_policy_features(clean, AS_OF)
    assert feats[0]["tenure_days"] == 1826  # 2021-11-20 -> 2026-11-20 (incl. leap days)
    assert feats[0]["premium_band"] == "1k_5k"
    assert feats[0]["is_active"] is True


def test_activity_features_window_and_recency():
    rows = [
        {"holder_id": "H1", "activity_date": "2026-11-19", "activity_type": "login"},
        {"holder_id": "H1", "activity_date": "2026-10-01", "activity_type": "login"},
        {"holder_id": "H2", "activity_date": "2026-11-20", "activity_type": "payment"},
    ]
    feats = engineer_activity_features(rows, AS_OF)
    h1 = next(f for f in feats if f["holder_id"] == "H1")
    assert h1["activity_count_30d"] == 1  # Oct 1 is 50 days back, outside the window
    assert h1["days_since_last_activity"] == 1
    assert h1["total_activities"] == 2
