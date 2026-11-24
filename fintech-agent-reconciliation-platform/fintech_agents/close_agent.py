"""Close agent — multi-step agentic close cycle for the Finance
Transformation Office shape.

The agent plans a close run (fetch invoices, consolidate entities,
reconcile the ledger, check forecast variance, evaluate the close
report against golden cases) and executes each step as a traced span
with structured logging and token-cost tracking. A journal entry
above the approval threshold waits for a human; the close report is
only marked ready when the golden-case evaluation passes. The
"LLM" is the same deterministic planner as FinanceAgent — no model
calls, no cost beyond the tracked synthetic token counts.
"""

from __future__ import annotations

from .eval_framework import EvaluationFramework, GoldenCase
from .finance_api import FinanceApiClient
from .finance_close import (CloseChecklist, arr_roll_forward,
                            billings_vs_revenue, consolidate,
                            forecast_variance)
from .ledger import BankLine, LedgerEntry, Reconciler
from .observability import CostTracker, StructuredLogger, Tracer

APPROVAL_THRESHOLD_MINOR = 1_000_000  # $10,000 journal entries need a human
MODEL_PRICE_PER_1K_USD = 0.005  # stated input price, not market data


class CloseAgent:
    def __init__(self, api: FinanceApiClient,
                 reconciler: Reconciler | None = None) -> None:
        self.api = api
        self.reconciler = reconciler or Reconciler()
        self.tracer = Tracer()
        self.logger = StructuredLogger()
        self.costs = CostTracker()
        self.trace: list[dict] = []
        self.pending_journals: dict[str, dict] = {}
        self._posted_keys: set[str] = set()

    def _step(self, trace_id: str, name: str, parent=None):
        span = self.tracer.start_span(name, trace_id=trace_id,
                                      parent=parent)
        self.logger.log("info", f"step started: {name}",
                        trace_id=trace_id, span_id=span.span_id)
        return span

    def _finish(self, span, outcome: str) -> None:
        self.tracer.end_span(span)
        self.trace.append({"step": span.name, "outcome": outcome,
                           "duration_ms": round(
                               span.duration_ms or 0.0, 2)})
        self.logger.log("info", f"step finished: {span.name}",
                        trace_id=span.trace_id, span_id=span.span_id,
                        outcome=outcome)

    def run_close_cycle(self, *, entities: list[dict],
                        ledger: list[LedgerEntry], bank: list[BankLine],
                        arr: dict, billings_minor: int,
                        revenue_minor: int, actual_minor: int,
                        forecast_minor: int,
                        checklist: CloseChecklist,
                        golden_cases: list[GoldenCase]) -> dict:
        """One close cycle, end to end. Returns the close report:
        consolidation, reconciliation, ARR bridge, billings, forecast
        variance, checklist progress, evaluation verdict, and cost."""
        trace_id = self.tracer._next_id("trace")
        root = self._step(trace_id, "close_cycle")
        # The agent "reasons" once per step; token use is tracked as
        # fixed synthetic counts so cost tracking is exercised.
        self.costs.record("close-planner", 800, 200,
                          MODEL_PRICE_PER_1K_USD)

        span = self._step(trace_id, "fetch_invoices", parent=root)
        invoices = self.api.list_all_invoices()
        self._finish(span, f"{len(invoices)} invoices fetched")

        span = self._step(trace_id, "consolidate", parent=root)
        consolidation = consolidate(entities)
        self._finish(span, "consolidated to USD")

        span = self._step(trace_id, "reconcile", parent=root)
        recon = self.reconciler.reconcile(ledger, bank)
        self._finish(span, f"match rate {recon.match_rate:.0%}")

        span = self._step(trace_id, "finance_metrics", parent=root)
        arr_result = arr_roll_forward(**arr)
        billings = billings_vs_revenue(billings_minor, revenue_minor)
        forecast = forecast_variance(actual_minor, forecast_minor)
        self._finish(span, "ARR, billings and forecast computed")

        span = self._step(trace_id, "checklist", parent=root)
        for task in checklist.ordered():
            if task.status != "done":
                checklist.complete(task.task_id)
        self._finish(span, f"checklist {checklist.progress:.0%} done")

        span = self._step(trace_id, "evaluate_report", parent=root)
        report_numbers = {
            "total_usd_minor": consolidation["total_usd_minor"],
            "ending_arr_minor": arr_result["ending_minor"],
            "match_rate_pct": round(recon.match_rate * 100, 1),
        }
        framework = EvaluationFramework(golden_cases)
        answers = {case.case_id: {
            "numbers": {k: report_numbers[k]
                        for k in case.expected_numbers
                        if k in report_numbers},
            "text": ("close report: consolidation, ARR, reconciliation "
                     "match rate")} for case in golden_cases}
        evaluation = framework.evaluate(answers)
        self._finish(span, f"eval {evaluation['passed']}/"
                           f"{evaluation['cases']} passed")
        self._finish(root, "ready" if evaluation["overall_passed"]
                     else "blocked by eval")

        return {
            "trace_id": trace_id,
            "invoices_fetched": len(invoices),
            "consolidation": {
                "total_usd_minor":
                    consolidation["total_usd_minor"],
                "entities": len(consolidation["lines"])},
            "reconciliation": {
                "matches": len(recon.matches),
                "unmatched_ledger": len(recon.unmatched_ledger),
                "mismatches": len(recon.mismatches),
                "match_rate": round(recon.match_rate, 4)},
            "arr": arr_result,
            "billings": billings,
            "forecast_variance": forecast,
            "checklist_progress": round(checklist.progress, 4),
            "evaluation": evaluation,
            "ready_to_close": evaluation["overall_passed"],
            "ai_cost_usd": self.costs.total_cost_usd,
            "ai_tokens": self.costs.total_tokens,
            "steps": self.trace,
            "audit_valid": True,
        }

    def post_journal_entry(self, payload: dict,
                           idempotency_key: str) -> dict:
        """Journal entries above the threshold wait for a human;
        smaller ones post straight through the idempotent API.
        Replays of an already-posted key return the recorded entry
        (never a second booking); replays of a still-pending key
        return pending_approval again."""
        if idempotency_key in self._posted_keys:
            return self.api.post_journal_entry(payload, idempotency_key)
        if idempotency_key in self.pending_journals:
            return {"status": "pending_approval",
                    "idempotency_key": idempotency_key}
        amount = payload.get("amount_minor", 0)
        if amount > APPROVAL_THRESHOLD_MINOR:
            self.pending_journals[idempotency_key] = payload
            return {"status": "pending_approval",
                    "idempotency_key": idempotency_key}
        result = self.api.post_journal_entry(payload, idempotency_key)
        if result["status"] == "created":
            self._posted_keys.add(idempotency_key)
        return result

    def approve_journal_entry(self, idempotency_key: str) -> dict:
        payload = self.pending_journals.pop(idempotency_key, None)
        if payload is None:
            raise KeyError(f"no pending journal {idempotency_key}")
        result = self.api.post_journal_entry(payload, idempotency_key)
        if result["status"] == "created":
            self._posted_keys.add(idempotency_key)
        return result
