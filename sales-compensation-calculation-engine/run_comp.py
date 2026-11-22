"""End-to-end demo: seed reps, a versioned comp plan and deals, then run
crediting -> calculation -> adjustments -> payments, with an audit trail
and a three-way reconciliation. Writes comp_report.txt and comp_report.json.

All data is synthetic and seeded in code. No real company or customer data
appears anywhere in this project.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from comp_engine import (
    Adjustment, CompPlan, Deal, Rep, Tier,
    PlanRegistry, credit_deal, quota_attainment,
    calculate, apply_adjustments, build_payments, AuditLog, reconcile,
)
from comp_engine.adjustments import clawback_for, spiff, total_for_deal


def seed():
    reps = {
        "R1": Rep("R1", "Ana Ruiz", "West", Decimal("800000"), Decimal("90000"), date(2023, 3, 1)),
        "R2": Rep("R2", "Ben Okafor", "East", Decimal("600000"), Decimal("85000"), date(2024, 1, 15)),
        "R3": Rep("R3", "Cara Lin", "Central", Decimal("500000"), Decimal("80000"), date(2024, 6, 3)),
    }
    registry = PlanRegistry()
    registry.register(CompPlan(
        plan_id="FY26-AE", name="FY26 Account Executive Plan", version=1,
        effective_from=date(2026, 2, 1), effective_to=date(2026, 10, 31),
        tiers=(Tier(Decimal("0"), Decimal("0.06")),
               Tier(Decimal("0.50"), Decimal("0.08")),
               Tier(Decimal("1.00"), Decimal("0.10"))),
        accelerator_threshold=Decimal("1.0"), accelerator_multiplier=Decimal("1.5"),
        cap=Decimal("60000"), clawback_days=90))
    # Plan change mid-year: v2 raises the top tier rate from 10% to 12%.
    registry.register(CompPlan(
        plan_id="FY26-AE", name="FY26 Account Executive Plan", version=2,
        effective_from=date(2026, 11, 1),
        tiers=(Tier(Decimal("0"), Decimal("0.06")),
               Tier(Decimal("0.50"), Decimal("0.08")),
               Tier(Decimal("1.00"), Decimal("0.12"))),
        accelerator_threshold=Decimal("1.0"), accelerator_multiplier=Decimal("1.5"),
        cap=Decimal("60000"), clawback_days=90))
    deals = [
        Deal("D1001", "R1", Decimal("420000"), date(2026, 11, 5), "Payments", "West"),
        Deal("D1002", "R1", Decimal("380000"), date(2026, 11, 12), "Payments", "West",
             split_with=("R3",), split_pct=Decimal("0.20")),
        Deal("D1003", "R2", Decimal("150000"), date(2026, 11, 8), "Terminal", "East"),
        Deal("D1004", "R2", Decimal("90000"), date(2026, 9, 20), "Terminal", "East",
             status="refunded"),
        Deal("D1005", "R3", Decimal("210000"), date(2026, 11, 18), "Payments", "Central"),
    ]
    return reps, registry, deals


def run():
    reps, registry, deals = seed()
    audit = AuditLog()
    # Crediting: accumulate credited amounts per rep for the period.
    credited: dict[str, Decimal] = {}
    for deal in deals:
        for rep_id, amount in credit_deal(deal, reps).items():
            credited[rep_id] = credited.get(rep_id, Decimal("0")) + amount
        audit.record("deal_credited", deal.deal_id, f"status={deal.status}")

    # Calculation under the plan version effective on each deal's close date.
    results = []
    for deal in deals:
        if deal.status != "closed_won":
            continue
        plan = registry.effective_plan("FY26-AE", deal.close_date)
        for rep_id, amount in credit_deal(deal, reps).items():
            rep_attainment = quota_attainment(reps[rep_id], credited[rep_id])
            result = calculate(deal.deal_id, rep_id, amount, rep_attainment, plan)
            results.append(result)
            audit.record("commission_calculated", deal.deal_id,
                         f"rep={rep_id} plan_v{plan.version} rate={result.rate} "
                         f"gross={result.gross_commission}")

    # Adjustments: the refunded September deal claws back, plus a SPIFF.
    adjustments: list[Adjustment] = []
    refunded = next(d for d in deals if d.deal_id == "D1004")
    claw = clawback_for(refunded, Decimal("7200"), registry.effective_plan("FY26-AE", refunded.close_date),
                        date(2026, 11, 10))
    if claw is not None:
        adjustments.append(claw)
        audit.record("clawback", claw.deal_id, f"amount={claw.amount} reason={claw.reason}")
    adjustments.append(spiff("SPIFF-1", "D1005", "R3", Decimal("1500"),
                             "Q4 new-logo SPIFF", date(2026, 11, 18)))
    audit.record("spiff", "D1005", "amount=1500")

    for result in results:
        apply_adjustments(result, total_for_deal(adjustments, result.deal_id))
    # A clawback has no commission result of its own (the deal was refunded),
    # so it reduces the rep's next payout: apply it to that rep's first result.
    for adj in adjustments:
        if adj.kind == "clawback":
            rep_results = [r for r in results if r.rep_id == adj.rep_id]
            if rep_results:
                apply_adjustments(rep_results[0], rep_results[0].adjustments + adj.amount)

    payments = build_payments(results, "2026-11")
    for payment in payments:
        audit.record("payment_scheduled", payment.payment_id,
                     f"rep={payment.rep_id} payable={payment.payable}")

    findings = reconcile(deals, results, payments, "2026-11")
    chain_ok = audit.verify()
    return {
        "reps": len(reps),
        "deals": len(deals),
        "results": len(results),
        "total_net": str(sum(r.net_commission for r in results)),
        "payments": len(payments),
        "total_payable": str(sum(p.payable for p in payments)),
        "findings": [f"{f.entity_id}: {f.kind} — {f.detail}" for f in findings],
        "audit_events": len(audit.events()),
        "audit_chain_ok": chain_ok,
        "plan_versions": len(registry.versions("FY26-AE")),
    }


def main():
    summary = run()
    lines = [
        "Sales Compensation Calculation Engine — demo run",
        f"Reps: {summary['reps']} | Deals: {summary['deals']} | Results: {summary['results']}",
        f"Plan versions: {summary['plan_versions']} | Total net commission: ${summary['total_net']}",
        f"Payments: {summary['payments']} | Total payable (after 10% holdback): ${summary['total_payable']}",
        f"Audit events: {summary['audit_events']} | Audit chain valid: {summary['audit_chain_ok']}",
        f"Reconciliation findings: {len(summary['findings'])}",
    ]
    for finding in summary["findings"]:
        lines.append(f"  - {finding}")
    text = "\n".join(lines) + "\n"
    print(text, end="")
    open("comp_report.txt", "w").write(text)
    json.dump(summary, open("comp_report.json", "w"), indent=2)


if __name__ == "__main__":
    main()
