"""Demo: a Finance AI close cycle — fetch, consolidate, reconcile,
variance, evaluate, report.

Run:  python run_close_demo.py
Expected: 5 invoices fetched, consolidation $84,300.00, 3/4 ledger
entries matched, ARR $115,000.00 ending at 100.0% NRR, forecast
variance +2.0% (not flagged), checklist 100% done, eval 1/1 passed,
close ready, a $50 journal entry posted and a $25,000 one held for
approval then posted after approval, AI cost $0.005.
"""

from fintech_agents.close_agent import CloseAgent
from fintech_agents.eval_framework import GoldenCase
from fintech_agents.finance_api import FakeErpTransport, FinanceApiClient
from fintech_agents.finance_close import CloseChecklist, CloseTask
from fintech_agents.ledger import BankLine, LedgerEntry

ENTITIES = [
    {"entity": "Veeam US", "currency": "USD",
     "revenue_minor": 5_000_000, "fx_to_usd": 1.0},
    {"entity": "Veeam EU", "currency": "EUR",
     "revenue_minor": 2_000_000, "fx_to_usd": 1.08},
    {"entity": "Veeam UK", "currency": "GBP",
     "revenue_minor": 1_000_000, "fx_to_usd": 1.27},
]

INVOICES = [{"invoice_id": f"INV-20{i}", "amount_minor": 100_000 * i}
            for i in range(1, 6)]


def main() -> None:
    client = FinanceApiClient(FakeErpTransport(INVOICES))
    agent = CloseAgent(client)
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
        CloseTask("accrue", "Post accruals", "controllership"),
        CloseTask("reconcile", "Reconcile subledgers", "controllership",
                  ["accrue"]),
        CloseTask("consolidate", "Consolidate entities", "controllership",
                  ["reconcile"]),
        CloseTask("forecast", "Forecast variance review", "fp&a",
                  ["consolidate"]),
        CloseTask("report", "Close report to leadership", "fp&a",
                  ["forecast"]),
    ])
    golden = [GoldenCase(
        "close-nov-2026",
        source_numbers={"total_usd_minor": 8_430_000,
                        "ending_arr_minor": 11_500_000,
                        "match_rate_pct": 75.0},
        expected_numbers={"total_usd_minor": 8_430_000,
                          "ending_arr_minor": 11_500_000,
                          "match_rate_pct": 75.0},
        expected_fields=["close report"])]
    report = agent.run_close_cycle(
        entities=ENTITIES, ledger=ledger, bank=bank,
        arr={"start_minor": 10_000_000, "new_minor": 1_500_000,
             "expansion_minor": 500_000, "churn_minor": 400_000,
             "contraction_minor": 100_000},
        billings_minor=9_000_000, revenue_minor=8_430_000,
        actual_minor=10_200_000, forecast_minor=10_000_000,
        checklist=checklist, golden_cases=golden)
    print(f"invoices fetched: {report['invoices_fetched']}")
    total = report["consolidation"]["total_usd_minor"] / 100
    print(f"consolidation: ${total:,.2f} across "
          f"{report['consolidation']['entities']} entities")
    rec = report["reconciliation"]
    print(f"reconciliation: {rec['matches']} matched, "
          f"{rec['unmatched_ledger']} unmatched "
          f"(match rate {rec['match_rate']:.0%})")
    arr = report["arr"]
    print(f"ARR: ending ${arr['ending_minor'] / 100:,.2f}, "
          f"NRR {arr['net_revenue_retention_pct']}%")
    bill = report["billings"]
    print(f"billings vs revenue: deferred change "
          f"${bill['deferred_revenue_change_minor'] / 100:,.2f}")
    fc = report["forecast_variance"]
    print(f"forecast variance: {fc['variance_pct']}% "
          f"flagged={fc['flagged']}")
    print(f"checklist: {report['checklist_progress']:.0%} done")
    ev = report["evaluation"]
    print(f"eval: {ev['passed']}/{ev['cases']} golden cases passed; "
          f"close ready: {report['ready_to_close']}")
    print(f"AI cost: ${report['ai_cost_usd']} "
          f"({report['ai_tokens']} tokens)")

    small = agent.post_journal_entry(
        {"account": "accruals", "amount_minor": 5000}, "je-1")
    print(f"journal je-1 ($50): {small['status']}")
    big = agent.post_journal_entry(
        {"account": "accruals", "amount_minor": 2_500_000}, "je-2")
    print(f"journal je-2 ($25,000): {big['status']} (needs approval)")
    approved = agent.approve_journal_entry("je-2")
    print(f"journal je-2 after approval: {approved['status']}")
    replay = agent.post_journal_entry(
        {"account": "accruals", "amount_minor": 5000}, "je-1")
    print(f"replay je-1: {replay['status']} (no double booking)")
    print(f"steps: {[s['step'] for s in report['steps']]}")


if __name__ == "__main__":
    main()
