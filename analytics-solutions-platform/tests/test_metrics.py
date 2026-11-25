import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics_solutions.metrics import MetricRegistry, MetricRegistryError, compute_metrics


def _registry():
    r = MetricRegistry()
    r.register("active_policies", "Count of active policies", "count_active_policies",
               "analytics-eng", "policy", ["fact_policy_activity"])
    r.register("active_premium_total", "Total premium of active policies", "total_premium_active",
               "analytics-eng", "policy", ["fact_policy_activity"])
    r.register("active_policy_share", "Share of policies active", "active_policy_share",
               "analytics-eng", "policy", ["fact_policy_activity"])
    return r


def test_register_and_compute_known_values():
    facts = [
        {"is_active": True, "premium_annual": 1000.0, "activity_count_30d": 2},
        {"is_active": True, "premium_annual": 3000.0, "activity_count_30d": 0},
        {"is_active": False, "premium_annual": 500.0, "activity_count_30d": 9},
    ]
    values = compute_metrics(_registry(), facts)
    assert values["active_policies"] == 2
    assert values["active_premium_total"] == 4000.0
    assert values["active_policy_share"] == round(2 / 3, 4)


def test_conflicting_redefinition_rejected_identical_reregistration_ok():
    r = _registry()
    with pytest.raises(MetricRegistryError):
        r.register("active_policies", "Count of active policies", "count_active_policies",
                   "someone-else", "policy", ["fact_policy_activity"])
    # identical re-registration is a no-op, not an error
    r.register("active_policies", "Count of active policies", "count_active_policies",
               "analytics-eng", "policy", ["fact_policy_activity"])


def test_unregistered_metric_and_unknown_formula_raise():
    r = MetricRegistry()
    with pytest.raises(MetricRegistryError):
        r.get("nope")
    r.register("weird", "Weird", "not_a_formula", "eng", "policy", ["fact_policy_activity"])
    with pytest.raises(MetricRegistryError):
        compute_metrics(r, [])


def test_empty_facts_compute_zero_safely():
    values = compute_metrics(_registry(), [])
    assert values["active_policies"] == 0
    assert values["active_premium_total"] == 0
    assert values["active_policy_share"] == 0.0
