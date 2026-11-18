"""Tests for the agents and the full pipeline."""

from agentic_stats.agents import AnalystAgent, PlannerAgent, ValidatorAgent
from agentic_stats.data import build_dataset
from agentic_stats.pipeline import render_report, run_pipeline


def test_planner_returns_ordered_steps():
    plan = PlannerAgent().plan("Does the treatment work?")
    assert plan["question"] == "Does the treatment work?"
    assert len(plan["steps"]) == 6
    assert plan["steps"][-1]["action"] == "validate"


def test_dataset_shape_and_ground_truth():
    rows = build_dataset()
    assert len(rows) == 240
    assert sum(1 for r in rows if r["arm"] == "treatment") == 120
    assert sum(1 for r in rows if r["arm"] == "control") == 120
    # Primary outcome really is higher under treatment; secondary is not.
    import statistics

    pt = statistics.mean(r["primary"] for r in rows if r["arm"] == "treatment")
    pc = statistics.mean(r["primary"] for r in rows if r["arm"] == "control")
    assert 5.0 < pt - pc < 11.0
    st = statistics.mean(r["secondary"] for r in rows if r["arm"] == "treatment")
    sc = statistics.mean(r["secondary"] for r in rows if r["arm"] == "control")
    assert abs(st - sc) < 6.0


def test_analyst_states_four_claims():
    claims = AnalystAgent().analyse(build_dataset())
    assert [c["id"] for c in claims] == ["C1", "C2", "C3", "C4"]
    assert all(0.0 <= c["p"] <= 1.0 for c in claims)
    # The primary-effect claim is strongly significant even uncorrected.
    assert claims[0]["p"] < 0.001


def test_validator_passes_real_effects_and_rejects_false_ones():
    rows = build_dataset()
    claims = AnalystAgent().analyse(rows)
    results = ValidatorAgent().validate(rows, claims)
    verdicts = {r["id"]: r["verdict"] for r in results}
    # Real primary effect and real responder-rate effect survive.
    assert verdicts["C1"] == "PASS"
    assert verdicts["C3"] == "PASS"
    # No secondary effect, and no extra subgroup benefit: both must fail.
    assert verdicts["C2"] == "FAIL"
    assert verdicts["C4"] == "FAIL"


def test_validator_reports_effect_sizes_and_cis():
    rows = build_dataset()
    claims = AnalystAgent().analyse(rows)
    results = ValidatorAgent().validate(rows, claims)
    c1 = next(r for r in results if r["id"] == "C1")
    assert c1["ci_95"][0] > 0  # CI excludes zero
    assert c1["cohens_d"] > 0.5
    assert c1["power"] > 0.9
    c4 = next(r for r in results if r["id"] == "C4")
    assert c4["interaction_p"] > 0.05  # no real interaction


def test_pipeline_report_counts():
    report = run_pipeline()
    assert report["n_rows"] == 240
    assert report["passed"] + report["failed"] == 4
    assert report["passed"] == 2
    assert report["failed"] == 2
    text = render_report(report)
    assert "C1 [PASS]" in text
    assert "C2 [FAIL]" in text
    assert "C3 [PASS]" in text
    assert "C4 [FAIL]" in text
