import pytest

from airload.load_plan import COMPARTMENTS, LoadPlan


def test_demo_plan_finalizes_inside_envelope():
    plan = LoadPlan(flight="AMZ101")
    plan.add_cargo("AKE12345", "FWD", 8_500.0)
    plan.add_cargo("AKE12346", "AFT", 7_200.0)
    plan.add_cargo("BULK01", "BULK", 2_800.0)
    plan.add_fuel(28_000.0)
    result = plan.finalize()
    assert result.within_envelope
    assert result.total_weight_lb == 136_500.0
    assert plan.compartment_totals() == {
        "FWD": 8_500.0,
        "AFT": 7_200.0,
        "BULK": 2_800.0,
    }


def test_compartment_overload_is_rejected():
    plan = LoadPlan(flight="AMZ101")
    with pytest.raises(ValueError, match="over its 12,000 lb limit"):
        plan.add_cargo("AKE99999", "FWD", 12_001.0)


def test_compartment_fill_then_overflow_is_rejected():
    plan = LoadPlan(flight="AMZ101")
    plan.add_cargo("AKE1", "BULK", 3_000.0)
    with pytest.raises(ValueError):
        plan.add_cargo("AKE2", "BULK", 1_500.0)


def test_unknown_compartment_is_rejected():
    plan = LoadPlan(flight="AMZ101")
    with pytest.raises(ValueError, match="unknown compartment"):
        plan.add_cargo("AKE1", "NOSE", 100.0)


def test_to_dict_requires_finalize():
    plan = LoadPlan(flight="AMZ101")
    plan.add_cargo("AKE1", "FWD", 1_000.0)
    with pytest.raises(ValueError, match="finalize"):
        plan.to_dict()


def test_to_dict_round_trip_matches_finalized_result():
    plan = LoadPlan(flight="AMZ101")
    plan.add_cargo("AKE1", "FWD", 5_000.0)
    plan.add_fuel(10_000.0)
    result = plan.finalize()
    data = plan.to_dict()
    assert data["flight"] == "AMZ101"
    assert data["total_weight_lb"] == result.total_weight_lb
    assert data["within_envelope"] is True
    assert len(data["items"]) == 2


def test_compartment_arms_are_documented():
    assert COMPARTMENTS["FWD"][0] < COMPARTMENTS["AFT"][0] < COMPARTMENTS["BULK"][0]
