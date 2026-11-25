"""Demo: AI spend management over the eval harness's traced tool calls.

Seeds a synthetic week of spend for two teams, sets budgets, ingests the
traced tool calls from a fresh eval run as spend events, then prints the
summary and any budget / spike alerts and writes spend_report.json.

All data is synthetic. No real billing API is involved.
"""

import json

from agent_eval import (INVOICE_CASES, TRIAGE_CASES, InvoiceAgent,
                        SupportTriageAgent, ToolServer, run_suite)
from agent_eval.spend import Budget, SpendLedger
from agent_eval.tracer import Tracer

TEAMS = ["finance", "support"]
MODELS = ["gpt-4o-mini", "claude-sonnet"]


def seed_ledger():
    ledger = SpendLedger()
    ledger.set_budget(Budget(team="finance", monthly_cap_usd=0.50))
    ledger.set_budget(Budget(team="support", monthly_cap_usd=0.20))
    # A synthetic week: steady daily usage, then one spike day for finance.
    for i, day in enumerate(["2026-11-03", "2026-11-04", "2026-11-05",
                             "2026-11-06", "2026-11-07"]):
        ledger.ingest({"team": "finance", "model": "gpt-4o-mini",
                       "agent": "invoice-agent", "prompt_tokens": 20000,
                       "completion_tokens": 10000, "day": day})
        ledger.ingest({"team": "support", "model": "claude-haiku",
                       "agent": "support-triage-agent", "prompt_tokens": 15000,
                       "completion_tokens": 5000, "day": day})
        if i == 4:  # spike day: a bulk backfill run for finance
            ledger.ingest({"team": "finance", "model": "claude-sonnet",
                           "agent": "invoice-agent", "prompt_tokens": 200000,
                           "completion_tokens": 100000, "day": day})
    return ledger


def main():
    ledger = seed_ledger()
    # Feed one live eval run's traced calls in as spend events.
    tracer = Tracer()
    tools = ToolServer(tracer)
    run_suite(InvoiceAgent(tools), INVOICE_CASES)
    run_suite(SupportTriageAgent(tools), TRIAGE_CASES)
    ledger.from_tracer(tracer, team="finance", model="gpt-4o-mini",
                       day="2026-11-07", agent="eval-agent")
    summary = ledger.summary()
    alerts = [a.to_dict() for a in
              ledger.check_budgets() + ledger.daily_spike_alerts()]
    print(f"Events: {summary['event_count']}, "
          f"tokens: {summary['total_tokens']}, "
          f"cost: ${summary['total_cost_usd']:.4f}")
    print("By team:", summary["by_team"])
    print("By model:", summary["by_model"])
    if alerts:
        print("Alerts:")
        for alert in alerts:
            print(f"  [{alert['level']}] {alert['message']}")
    else:
        print("Alerts: none")
    report = {"summary": summary, "alerts": alerts}
    with open("spend_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Wrote spend_report.json")


if __name__ == "__main__":
    main()
