import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics_solutions.models import (DimensionLoadError, build_dim_advisor,
                                         build_dim_date, build_dim_holder,
                                         build_fact_policy_activity)

AS_OF = date(2026, 11, 20)


def test_dim_holder_assigns_stable_surrogates_and_rejects_dupes():
    rows, keys = build_dim_holder([
        {"holder_id": "H2", "holder_name": "B", "state": "WI", "segment": "core"},
        {"holder_id": "H1", "holder_name": "A", "state": "WI", "segment": "core"},
    ])
    assert keys == {"H1": 1, "H2": 2}  # sorted by natural key
    with pytest.raises(DimensionLoadError):
        build_dim_holder([{"holder_id": "H1"}, {"holder_id": "H1"}])


def test_dim_date_covers_range_and_marks_month_end():
    rows = build_dim_date(date(2026, 11, 29), date(2026, 12, 1))
    assert len(rows) == 3
    assert rows[0]["date_key"] == 20261129
    assert rows[1]["is_month_end"] is True  # Nov 30
    assert rows[2]["is_month_end"] is False


def test_fact_rejects_unknown_holder_or_advisor():
    _, hk = build_dim_holder([{"holder_id": "H1", "holder_name": "A", "state": "WI", "segment": "core"}])
    _, ak = build_dim_advisor([{"advisor_id": "A1", "advisor_name": "N", "office": "MKE"}])
    policies = [{"policy_id": "P1", "holder_id": "H9", "advisor_id": "A1",
                 "product": "term_life", "premium_annual": 1000.0,
                 "premium_band": "1k_5k", "tenure_days": 10, "is_active": True}]
    with pytest.raises(DimensionLoadError):
        build_fact_policy_activity(policies, [], hk, ak, AS_OF)
    policies[0]["holder_id"] = "H1"
    policies[0]["advisor_id"] = "A9"
    with pytest.raises(DimensionLoadError):
        build_fact_policy_activity(policies, [], hk, ak, AS_OF)


def test_fact_joins_features_and_defaults_activity_to_zero():
    _, hk = build_dim_holder([{"holder_id": "H1", "holder_name": "A", "state": "WI", "segment": "core"}])
    _, ak = build_dim_advisor([{"advisor_id": "A1", "advisor_name": "N", "office": "MKE"}])
    policies = [{"policy_id": "P1", "holder_id": "H1", "advisor_id": "A1",
                 "product": "term_life", "premium_annual": 1000.0,
                 "premium_band": "1k_5k", "tenure_days": 10, "is_active": True}]
    facts = build_fact_policy_activity(policies, [], hk, ak, AS_OF)
    assert facts[0]["holder_key"] == 1
    assert facts[0]["advisor_key"] == 1
    assert facts[0]["date_key"] == 20261120
    assert facts[0]["activity_count_30d"] == 0
