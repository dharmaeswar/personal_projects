import pytest

from fintech_agents.close_agent import CloseAgent
from fintech_agents.eval_framework import GoldenCase
from fintech_agents.finance_api import FakeErpTransport, FinanceApiClient
from fintech_agents.finance_close import CloseChecklist, CloseTask
from fintech_agents.ledger import BankLine, LedgerEntry


def _agent():
    invoices = [{"invoice_id": f"INV-{i}", "amount_minor": 100_000}
                for i in range(1, 6)]
    return CloseAgent(FinanceApiClient(FakeErpTransport(invoices)))


def _inputs():
    ledger = [
        LedgerEntry("e1", "AP", "INV-1001", 125000, "2026-11-03"),
        LedgerEntry("e2", "AR", "INV-1002", 80000, "2026-11-05"),
        LedgerEntry("e3", "GL", "INV-1003", 45000, "2026-11-07"),
        LedgerEntry("e4", "AP", "INV-1004", 60000, "2026-11-09"),
    ]
    bank = [
        BankLine("b1", "INV-1001", 125000, "2026-11-03"),
        BankLine("b2", "INV-1002", 80000, "2026-11-06"),
        BankLine("b3", "INV-1003", 45000, "2026-11-07"),
    ]
    checklist = CloseChecklist([
        CloseTask("a", "Accrue", "controllership"),
        CloseTask("b", "Report", "fp&a", ["a"]),
    ])
    golden = [GoldenCase(
        "close-nov",
        source_numbers={"total_usd_minor": 8_430_000,
                        "ending_arr_minor": 11_500_000,
                        "match_rate_pct": 75.0},
        expected_numbers={"total_usd_minor": 8_430_000,
                          "ending_arr_minor": 11_500_000,
                          "match_rate_pct": 75.0},
        expected_fields=["close report"])]
    return {
        "entities": [
            {"entity": "US", "currency": "USD",
             "revenue_minor": 5_000_000, "fx_to_usd": 1.0},
            {"entity": "EU", "currency": "EUR",
             "revenue_minor": 2_000_000, "fx_to_usd": 1.08},
            {"entity": "UK", "currency": "GBP",
             "revenue_minor": 1_000_000, "fx_to_usd": 1.27},
        ],
        "ledger": ledger, "bank": bank,
        "arr": {"start_minor": 10_000_000, "new_minor": 1_500_000,
                "expansion_minor": 500_000, "churn_minor": 400_000,
                "contraction_minor": 100_000},
        "billings_minor": 9_000_000, "revenue_minor": 8_430_000,
        "actual_minor": 10_200_000, "forecast_minor": 10_000_000,
        "checklist": checklist, "golden_cases": golden,
    }


def test_close_cycle_ready_when_eval_passes():
    report = _agent().run_close_cycle(**_inputs())
    assert report["ready_to_close"] is True
    assert report["consolidation"]["total_usd_minor"] == 8_430_000
    assert report["reconciliation"]["match_rate"] == 0.75
    assert report["arr"]["ending_minor"] == 11_500_000
    assert report["checklist_progress"] == 1.0
    assert report["evaluation"]["overall_passed"] is True
    assert report["ai_cost_usd"] == 0.005
    assert report["ai_tokens"] == 1000
    assert len(report["steps"]) == 7  # root + 6 steps
    assert report["steps"][-1]["step"] == "close_cycle"  # root finishes last


def test_close_cycle_blocked_when_golden_case_wrong():
    inputs = _inputs()
    inputs["golden_cases"] = [GoldenCase(
        "close-nov",
        source_numbers={"total_usd_minor": 8_430_000},
        expected_numbers={"total_usd_minor": 1},
        expected_fields=["close report"])]
    report = _agent().run_close_cycle(**inputs)
    assert report["ready_to_close"] is False
    assert report["evaluation"]["overall_passed"] is False


def test_small_journal_posts_directly():
    agent = _agent()
    result = agent.post_journal_entry(
        {"account": "accruals", "amount_minor": 5000}, "je-1")
    assert result["status"] == "created"


def test_large_journal_needs_approval_then_posts_once():
    agent = _agent()
    held = agent.post_journal_entry(
        {"account": "accruals", "amount_minor": 2_500_000}, "je-2")
    assert held["status"] == "pending_approval"
    posted = agent.approve_journal_entry("je-2")
    assert posted["status"] == "created"
    replay = agent.post_journal_entry(
        {"account": "accruals", "amount_minor": 2_500_000}, "je-2")
    assert replay["status"] == "replayed"


def test_approve_unknown_journal_raises():
    with pytest.raises(KeyError):
        _agent().approve_journal_entry("nope")
