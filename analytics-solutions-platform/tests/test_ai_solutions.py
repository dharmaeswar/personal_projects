"""Tests for the AI solutions layer (ai_solutions.py)."""

from datetime import date

import pytest

from analytics_solutions.ai_solutions import (
    AISolutionsError,
    DriverError,
    GroundingError,
    driver_analysis,
    enrich_client_records,
    plan_solution,
    run_solution,
    validate_grounding,
)
from analytics_solutions.discovery import register_product
from analytics_solutions.metrics import MetricRegistry

AS_OF = date(2026, 11, 20)


def _clients():
    return [
        {"client_id": "C-1", "segment": "retail", "channel": "portal", "signup_date": "2024-01-10"},
        {"client_id": "C-2", "segment": "retail", "channel": "portal", "signup_date": "2024-02-10"},
        {"client_id": "C-3", "segment": "retail", "channel": "branch", "signup_date": "2024-03-10"},
        {"client_id": "C-4", "segment": "commercial", "channel": "portal", "signup_date": "2023-05-01"},
        {"client_id": "C-5", "segment": "commercial", "channel": "branch", "signup_date": "2023-06-01"},
        {"client_id": "C-6", "segment": "commercial", "channel": "portal", "signup_date": "2023-07-01"},
    ]


def _txns():
    rows = []
    for i, cid in enumerate(["C-1", "C-2", "C-3", "C-4", "C-5", "C-6"]):
        for j in range(i + 1):
            rows.append({"txn_id": f"T-{cid}-{j}", "client_id": cid,
                         "amount": 100.0 * (i + 1), "txn_date": "2026-11-1%d" % (j % 9)})
    return rows


def _acts():
    counts = {"C-1": 1, "C-2": 2, "C-3": 1, "C-4": 3, "C-5": 2, "C-6": 4}
    acts = []
    for cid, n in counts.items():
        for k in range(n):
            acts.append({"client_id": cid, "activity_date": "2026-11-1%d" % (5 + k),
                         "activity_type": "portal_login"})
    return acts


def _registry_and_facts():
    reg = MetricRegistry()
    reg.register("active_policies", "count of active policies", "count_active_policies",
                 "analytics", "policy", ["fact_policy_activity"])
    facts = [{"is_active": True, "premium_annual": 1000.0, "activity_count_30d": 2}
             for _ in range(3)]
    facts.append({"is_active": False, "premium_annual": 500.0, "activity_count_30d": 0})
    return reg, facts


def _catalog():
    catalog = []
    register_product(catalog, {
        "product_id": "P-1", "name": "Client volume by segment",
        "domain": "client services", "owner": "analytics",
        "description": "30-day transaction volume by client segment",
        "keywords": ["volume", "segment", "client"],
        "source_datasets": ["fact_client_activity"],
        "freshness_sla_hours": 24, "quality_score": 90})
    return catalog


# --- enrichment ---

def test_enrichment_window_aggregates():
    enriched, quarantined = enrich_client_records(_clients(), _txns(), _acts(), AS_OF)
    assert quarantined == []
    c6 = next(r for r in enriched if r["client_id"] == "C-6")
    assert c6["txn_count_30d"] == 6
    assert c6["txn_volume_30d"] == 3600.0
    assert c6["avg_ticket_30d"] == 600.0
    assert c6["activity_count_30d"] == 4
    assert c6["recency_days"] == 5


def test_enrichment_quarantines_bad_rows():
    txns = _txns() + [
        {"txn_id": "T-BAD-1", "client_id": "C-1", "amount": -50.0, "txn_date": "2026-11-10"},
        {"txn_id": "T-BAD-2", "client_id": "C-1", "amount": None, "txn_date": "2026-11-10"},
        {"txn_id": "T-BAD-3", "client_id": "C-99", "amount": 10.0, "txn_date": "2026-11-10"},
        {"txn_id": "T-C-1-0", "client_id": "C-1", "amount": 10.0, "txn_date": "2026-11-10"},
        {"txn_id": "T-BAD-4", "client_id": "C-1", "amount": 10.0, "txn_date": "not-a-date"},
    ]
    enriched, quarantined = enrich_client_records(_clients(), txns, _acts(), AS_OF)
    assert len(quarantined) == 5
    reasons = {q["quarantine_reason"] for q in quarantined}
    assert reasons == {"negative or missing amount", "unknown client_id",
                       "duplicate or missing txn_id", "unparseable txn_date"}
    c1 = next(r for r in enriched if r["client_id"] == "C-1")
    assert c1["txn_count_30d"] == 1  # bad rows never enter the KPIs


def test_enrichment_anomaly_flag():
    clients = _clients()
    txns = [{"txn_id": f"T-{i}", "client_id": "C-1", "amount": 100.0, "txn_date": "2026-11-10"}
            for i in range(3)]
    txns += [{"txn_id": f"U-{i}", "client_id": "C-2", "amount": 100.0, "txn_date": "2026-11-10"}
             for i in range(3)]
    txns += [{"txn_id": f"V-{i}", "client_id": "C-3", "amount": 100.0, "txn_date": "2026-11-10"}
             for i in range(3)]
    # C-1 gets one huge month; retail segment has 3 clients so it is scored.
    txns.append({"txn_id": "BIG-1", "client_id": "C-1", "amount": 100000.0, "txn_date": "2026-11-10"})
    enriched, _ = enrich_client_records(clients, txns, [], AS_OF)
    c1 = next(r for r in enriched if r["client_id"] == "C-1")
    assert c1["anomaly"] is False  # z-score with 3 points cannot exceed 2.0
    assert all(r["anomaly"] is False for r in enriched)


def test_enrichment_bad_window():
    with pytest.raises(AISolutionsError):
        enrich_client_records(_clients(), [], [], AS_OF, window_days=0)


# --- driver analysis ---

def test_driver_analysis_names_strongest_driver():
    rows = [{"txn_volume_30d": 10 * c + 2 * a, "txn_count_30d": c, "activity_count_30d": a}
            for c, a in [(1, 5), (2, 1), (3, 4), (4, 2), (5, 3), (6, 0)]]
    out = driver_analysis(rows, "txn_volume_30d", ["txn_count_30d", "activity_count_30d"])
    assert out["strongest_driver"] == "txn_count_30d"
    assert out["coefficients"]["txn_count_30d"] == pytest.approx(10.0, abs=1e-6)
    assert out["coefficients"]["activity_count_30d"] == pytest.approx(2.0, abs=1e-6)
    assert out["r_squared"] == pytest.approx(1.0, abs=1e-6)
    assert out["n"] == 6
    assert "txn_count_30d is the strongest driver" in out["readout"]


def test_driver_analysis_skips_incomplete_rows():
    rows = [{"txn_volume_30d": 10.0, "txn_count_30d": 1, "activity_count_30d": 2},
            {"txn_volume_30d": 20.0, "txn_count_30d": 2, "activity_count_30d": None},
            {"txn_volume_30d": 30.0, "txn_count_30d": 3, "activity_count_30d": 5},
            {"txn_volume_30d": 40.0, "txn_count_30d": 4, "activity_count_30d": 1},
            {"txn_volume_30d": 50.0, "txn_count_30d": 5, "activity_count_30d": 4}]
    out = driver_analysis(rows, "txn_volume_30d", ["txn_count_30d", "activity_count_30d"])
    assert out["skipped"] == 1
    assert out["n"] == 4


def test_driver_analysis_too_few_rows():
    with pytest.raises(DriverError):
        driver_analysis([{"y": 1.0, "a": 1.0}], "y", ["a"])


def test_driver_analysis_collinear_features():
    rows = [{"y": float(i), "a": float(i), "b": float(i)} for i in range(1, 7)]
    with pytest.raises(DriverError):
        driver_analysis(rows, "y", ["a", "b"])


# --- grounding ---

def test_validate_grounding_flags_ungrounded_number():
    ungrounded = validate_grounding("volume is 123.45 and count is 6",
                                    {"count": 6})
    assert ungrounded == ["123.45"]


def test_validate_grounding_passes_when_all_numbers_traced():
    assert validate_grounding("volume is 123.45 and count is 6",
                              {"volume": 123.45, "count": 6}) == []


# --- planner ---

def test_plan_solution_includes_enrichment_for_driver_question():
    plan = plan_solution("why does client segment volume differ?")
    tools = [s["tool"] for s in plan]
    assert tools.index("run_enrichment") < tools.index("driver_analysis")
    assert "get_metric" in tools
    assert "find_dataset" in tools


def test_plan_solution_metric_only_question():
    plan = plan_solution("how many active policies are there?")
    assert [s["tool"] for s in plan] == ["get_metric", "find_dataset"]


# --- end-to-end runner ---

def test_run_solution_grounded_answer():
    reg, facts = _registry_and_facts()
    out = run_solution("which client segment leads 30-day volume and what drives it?",
                       registry=reg, facts=facts, catalog=_catalog(),
                       clients=_clients(), transactions=_txns(), activities=_acts(),
                       as_of=AS_OF, run_id="test-run-1", seed=7)
    assert out["top_segment"] == "commercial"
    assert "commercial leads 30-day volume" in out["answer"]
    assert "strongest driver" in out["answer"]
    assert out["input_hash"]
    assert out["tool_calls"]
    assert validate_grounding(out["answer"], out["evidence"]) == []


def test_run_solution_reproducible_hash():
    reg, facts = _registry_and_facts()
    kwargs = dict(registry=reg, facts=facts, catalog=_catalog(),
                  clients=_clients(), transactions=_txns(), activities=_acts(),
                  as_of=AS_OF, run_id="r", seed=7)
    assert run_solution("which segment leads volume?", **kwargs)["input_hash"] == \
        run_solution("which segment leads volume?", **kwargs)["input_hash"]


def test_run_solution_rejects_ungrounded_answer(monkeypatch):
    # Force the grounding check to report an ungrounded number: the runner
    # must refuse to ship the answer instead of reporting it.
    import analytics_solutions.ai_solutions as mod
    monkeypatch.setattr(mod, "validate_grounding", lambda answer, evidence: ["999.99"])
    reg, facts = _registry_and_facts()
    with pytest.raises(GroundingError):
        run_solution("which client segment leads 30-day volume?",
                     registry=reg, facts=facts, catalog=_catalog(),
                     clients=_clients(), transactions=_txns(), activities=_acts(),
                     as_of=AS_OF, run_id="r2", seed=1)
