"""Demo: reconcile a month, report variance, pay out, audit everything.

Run:  python run_fintech.py
Expected: 3/4 ledger entries matched (1 break), variance flagged at
+12.5%, a $50 payout executed, a $25,000 payout held for approval then
approved and executed, audit chain valid, eval 2/2 golden cases passed.
"""

from fintech_agents import FinanceAgent, McpServer
from fintech_agents.ledger import BankLine, LedgerEntry
from fintech_agents.mcp import Token

READER = Token("tok-reader", "agent-finance", {"finance:read"})
PAYER = Token("tok-payer", "agent-finance",
              {"finance:read", "finance:payout"})
APPROVER = Token("tok-approver", "finance-lead",
                 {"finance:read", "finance:approve"})


def main() -> None:
    agent = FinanceAgent(McpServer())
    ledger = [
        LedgerEntry("e1", "AP", "INV-1001", 125000, "2026-11-03", "vendor A"),
        LedgerEntry("e2", "AR", "INV-1002", 80000, "2026-11-05", "client B"),
        LedgerEntry("e3", "GL", "INV-1003", 45000, "2026-11-07", "accrual"),
        LedgerEntry("e4", "AP", "INV-1004", 60000, "2026-11-09", "vendor C"),
    ]
    bank = [
        BankLine("b1", "INV-1001", 125000, "2026-11-03"),
        BankLine("b2", "INV-1002", 80000, "2026-11-06"),  # 1 day later
        BankLine("b3", "INV-1003", 45000, "2026-11-07"),
    ]
    outcome = agent.run_reconciliation(READER, ledger, bank)
    print(f"reconciled: {len(outcome.matches)} matched, "
          f"{len(outcome.unmatched_ledger)} unmatched ledger, "
          f"{len(outcome.unmatched_bank)} unmatched bank, "
          f"{len(outcome.mismatches)} mismatches "
          f"(match rate {outcome.match_rate:.0%})")

    report = agent.run_variance_report(READER, 1_125_000, 1_000_000)
    print(f"variance: actual {report['actual_minor']} vs budget "
          f"{report['budget_minor']} = {report['variance_pct']}% "
          f"flagged={report['flagged']}")

    small = agent.run_payout(PAYER, "pay-1", "vendor A", 5000)
    agent.execute_payout(PAYER, "pay-1")
    print(f"payout pay-1 ($50): {small.status}")

    big = agent.run_payout(PAYER, "pay-2", "vendor C", 2_500_000)
    print(f"payout pay-2 ($25,000): {big.status} (needs approval)")
    try:
        agent.execute_payout(PAYER, "pay-2")
    except PermissionError as exc:
        print(f"execute before approval blocked: {exc}")
    agent.approve_payout(APPROVER, "pay-2")
    agent.execute_payout(PAYER, "pay-2")
    print(f"payout pay-2 after approval: "
          f"{agent.payouts['pay-2'].status}")

    replay = agent.run_payout(PAYER, "pay-1", "vendor A", 5000)
    print(f"replay pay-1 returns the same payout, status {replay.status} "
          f"(no double payment)")

    golden = [
        {"ledger": ledger[:2], "bank": bank[:2],
         "expected_matches": 2, "expected_unmatched_ledger": 0},
        {"ledger": ledger[3:], "bank": [],
         "expected_matches": 0, "expected_unmatched_ledger": 1},
    ]
    score = agent.evaluate(READER, golden)
    print(f"eval: {score['passed']}/{score['cases']} golden cases passed")
    print(f"audit chain valid: {agent.audit.verify()} "
          f"({len(agent.audit.entries)} entries)")
    print(f"metrics: {agent.metrics.counters}")


if __name__ == "__main__":
    main()
