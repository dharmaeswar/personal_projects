from airload.load_plan import LoadPlan
from airload.verification import verify_items, verify_load_plan


def _good_plan() -> LoadPlan:
    plan = LoadPlan(flight="AMZ101")
    plan.add_cargo("AKE12345", "FWD", 8_500.0)
    plan.add_cargo("AKE12346", "AFT", 7_200.0)
    plan.add_fuel(28_000.0)
    plan.finalize()
    return plan


def _submitted(plan: LoadPlan) -> dict:
    data = plan.to_dict()
    data["compartments"] = plan.compartment_totals()
    return data


def test_correct_plan_passes_alv():
    plan = _good_plan()
    report = verify_load_plan(plan, _submitted(plan))
    assert report.passed
    assert report.discrepancies == []
    assert report.recomputed_weight_lb == 133_700.0


def test_tampered_weight_is_caught():
    plan = _good_plan()
    submitted = _submitted(plan)
    submitted["total_weight_lb"] += 5_000.0
    report = verify_load_plan(plan, submitted)
    assert not report.passed
    assert any(d.field == "total_weight_lb" for d in report.discrepancies)


def test_tampered_cg_is_caught():
    plan = _good_plan()
    submitted = _submitted(plan)
    submitted["cg_percent_mac"] += 3.0
    report = verify_load_plan(plan, submitted)
    assert not report.passed
    assert any(d.field == "cg_percent_mac" for d in report.discrepancies)


def test_tampered_compartment_total_is_caught():
    plan = _good_plan()
    submitted = _submitted(plan)
    submitted["compartments"]["FWD"] = 1_000.0
    report = verify_load_plan(plan, submitted)
    assert not report.passed
    assert any(d.field == "compartment:FWD" for d in report.discrepancies)


def test_small_rounding_differences_pass():
    plan = _good_plan()
    submitted = _submitted(plan)
    submitted["total_weight_lb"] += 10.0  # inside the 50 lb tolerance
    submitted["cg_percent_mac"] += 0.1  # inside the 0.5 % MAC tolerance
    report = verify_load_plan(plan, submitted)
    assert report.passed


def test_out_of_envelope_plan_fails_alv():
    plan = LoadPlan(flight="AMZ102")
    # Heavy aft load within compartment caps pushes CG past the aft limit.
    plan.add_cargo("AKE12346", "AFT", 10_000.0)
    plan.add_cargo("BULK01", "BULK", 4_000.0)
    plan.finalize()
    report = verify_load_plan(plan, _submitted(plan))
    assert not report.passed
    assert any(d.field == "envelope" for d in report.discrepancies)


def test_verify_items_returns_weight_balance_result():
    from airload.weight_balance import LoadItem

    result = verify_items([LoadItem("cargo:FWD:AKE1", 5_000.0, 480.0)])
    assert result.total_weight_lb == 95_000.0


def test_summary_names_the_flight_and_status():
    plan = _good_plan()
    report = verify_load_plan(plan, _submitted(plan))
    assert "AMZ101" in report.summary()
    assert "PASS" in report.summary()
