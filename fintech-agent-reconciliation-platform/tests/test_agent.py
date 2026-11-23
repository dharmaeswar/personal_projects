import pytest

from fintech_agents import FinanceAgent, McpServer
from fintech_agents.ledger import BankLine, LedgerEntry
from fintech_agents.mcp import Token

READER = Token("t-r", "agent", {"finance:read"})
PAYER = Token("t-p", "agent", {"finance:read", "finance:payout"})
APPROVER = Token("t-a", "lead", {"finance:read", "finance:approve"})
NO_SCOPE = Token("t-n", "agent", set())


def make_agent():
    return FinanceAgent(McpServer())


def test_reconciliation_counts_and_audit():
    agent = make_agent()
    out = agent.run_reconciliation(
        READER,
        [LedgerEntry("e1", "AP", "INV-1", 1000, "2026-11-03")],
        [BankLine("b1", "INV-1", 1000, "2026-11-03")])
    assert len(out.matches) == 1
    assert agent.metrics.counters["reconciliations"] == 1
    assert agent.audit.entries[-1].action == "reconcile"


def test_reconciliation_without_scope_raises():
    agent = make_agent()
    with pytest.raises(PermissionError):
        agent.run_reconciliation(NO_SCOPE, [], [])


def test_variance_flagged_above_threshold():
    agent = make_agent()
    report = agent.run_variance_report(READER, 1_125_000, 1_000_000)
    assert report["variance_pct"] == 12.5 and report["flagged"] is True
    calm = agent.run_variance_report(READER, 1_010_000, 1_000_000)
    assert calm["flagged"] is False


def test_small_payout_executes_without_approval():
    agent = make_agent()
    payout = agent.run_payout(PAYER, "pay-1", "vendor A", 5000)
    assert payout.status == "created"
    assert agent.execute_payout(PAYER, "pay-1").status == "executed"


def test_large_payout_needs_approval_first():
    agent = make_agent()
    payout = agent.run_payout(PAYER, "pay-2", "vendor C", 2_500_000)
    assert payout.status == "pending_approval"
    with pytest.raises(PermissionError):
        agent.execute_payout(PAYER, "pay-2")
    with pytest.raises(PermissionError):
        agent.approve_payout(PAYER, "pay-2")  # payer lacks approve scope
    agent.approve_payout(APPROVER, "pay-2")
    assert agent.execute_payout(PAYER, "pay-2").status == "executed"


def test_payout_replay_never_pays_twice():
    agent = make_agent()
    first = agent.run_payout(PAYER, "pay-1", "vendor A", 5000)
    agent.execute_payout(PAYER, "pay-1")
    again = agent.run_payout(PAYER, "pay-1", "vendor A", 5000)
    assert again is first
    assert agent.metrics.counters["payouts_executed"] == 1


def test_payout_without_scope_raises():
    agent = make_agent()
    with pytest.raises(PermissionError):
        agent.run_payout(READER, "pay-1", "vendor A", 5000)


def test_evaluate_scores_golden_cases():
    agent = make_agent()
    golden = [
        {"ledger": [LedgerEntry("e1", "AP", "INV-1", 1000, "2026-11-03")],
         "bank": [BankLine("b1", "INV-1", 1000, "2026-11-03")],
         "expected_matches": 1, "expected_unmatched_ledger": 0},
        {"ledger": [LedgerEntry("e2", "AP", "INV-2", 2000, "2026-11-04")],
         "bank": [],
         "expected_matches": 0, "expected_unmatched_ledger": 1},
    ]
    score = agent.evaluate(READER, golden)
    assert score == {"cases": 2, "passed": 2, "pass_rate": 1.0}


def test_audit_chain_verifies():
    agent = make_agent()
    agent.run_variance_report(READER, 1_100_000, 1_000_000)
    assert agent.audit.verify() is True
    agent.audit.entries[0].detail["variance_pct"] = 99.9
    assert agent.audit.verify() is False
