"""Finance agent — Bedrock-style orchestration over MCP tools.

The agent plans a workflow (reconcile, variance report, payout), calls
tools through the MCP server, and enforces the safety rules from the
posting: guardrails on every tool call, human-in-the-loop approval for
payouts above the threshold, evaluation against golden cases, and a
hash-chained audit trail for everything it does.

The planner is a fixed deterministic policy, not a model call, so runs
are reproducible. Payouts are idempotent on the caller-supplied payout
id: replaying the same payout returns the recorded outcome instead of
paying twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .ledger import (BankLine, LedgerEntry, Reconciler,
                     ReconciliationResult, variance)
from .mcp import McpServer, Token, Tool
from .observability import AuditLog, Metrics

APPROVAL_THRESHOLD_MINOR = 1_000_000  # $10,000 — payouts above need a human


@dataclass
class Payout:
    payout_id: str
    payee: str
    amount_minor: int
    status: str  # created | pending_approval | approved | executed


class FinanceAgent:
    def __init__(self, server: McpServer, *, reconciler=None) -> None:
        self.server = server
        self.reconciler = reconciler or Reconciler()
        self.audit = AuditLog()
        self.metrics = Metrics()
        self.payouts: dict[str, Payout] = {}
        self._register_tools()

    def _register_tools(self) -> None:
        self.server.register(Tool(
            "reconcile", "finance:read",
            lambda p: {"result": "reconciled",
                       "ledger_count": len(p["ledger"]),
                       "bank_count": len(p["bank"])}))
        self.server.register(Tool(
            "variance.report", "finance:read",
            lambda p: variance(p["actual_minor"], p["budget_minor"])))
        self.server.register(Tool(
            "payout.create", "finance:payout",
            lambda p: {"payout_id": p["payout_id"],
                       "status": "created"}))

    # -- reconciliation --------------------------------------------------
    def run_reconciliation(self, token: Token, ledger: list[LedgerEntry],
                           bank: list[BankLine]) -> ReconciliationResult:
        result = self.server.invoke(
            token, "reconcile",
            {"ledger": [e.entry_id for e in ledger],
             "bank": [ln.line_id for ln in bank]})
        if not result.ok:
            raise PermissionError(result.reason)
        outcome = self.reconciler.reconcile(ledger, bank)
        # Hallucination check: the reported match rate must come from the
        # reconciler's own counts, never from a guessed number.
        self.metrics.inc("reconciliations")
        self.metrics.inc("matches", len(outcome.matches))
        self.metrics.inc("breaks", len(outcome.unmatched_ledger)
                         + len(outcome.unmatched_bank)
                         + len(outcome.mismatches))
        self.audit.append(token.subject, "reconcile", {
            "matches": len(outcome.matches),
            "unmatched_ledger": len(outcome.unmatched_ledger),
            "unmatched_bank": len(outcome.unmatched_bank),
            "mismatches": len(outcome.mismatches),
            "match_rate": round(outcome.match_rate, 4)})
        return outcome

    # -- variance --------------------------------------------------------
    def run_variance_report(self, token: Token, actual_minor: int,
                            budget_minor: int,
                            *, flag_threshold_pct: float = 5.0) -> dict:
        result = self.server.invoke(
            token, "variance.report",
            {"actual_minor": actual_minor, "budget_minor": budget_minor})
        if not result.ok:
            raise PermissionError(result.reason)
        report = dict(result.data)
        report["flagged"] = abs(report["variance_pct"]) > flag_threshold_pct
        self.metrics.inc("variance_reports")
        self.audit.append(token.subject, "variance.report", report)
        return report

    # -- payouts ---------------------------------------------------------
    def run_payout(self, token: Token, payout_id: str, payee: str,
                   amount_minor: int) -> Payout:
        existing = self.payouts.get(payout_id)
        if existing is not None:
            return existing  # idempotent replay: never pay twice
        result = self.server.invoke(
            token, "payout.create",
            {"payout_id": payout_id, "payee": payee,
             "amount_minor": amount_minor})
        if not result.ok:
            raise PermissionError(result.reason)
        status = ("pending_approval" if amount_minor > APPROVAL_THRESHOLD_MINOR
                  else "created")
        payout = Payout(payout_id, payee, amount_minor, status)
        self.payouts[payout_id] = payout
        self.metrics.inc("payouts_created")
        self.audit.append(token.subject, "payout.create", {
            "payout_id": payout_id, "payee": payee,
            "amount_minor": amount_minor, "status": status})
        return payout

    def approve_payout(self, approver: Token, payout_id: str) -> Payout:
        payout = self.payouts.get(payout_id)
        if payout is None:
            raise KeyError(f"unknown payout {payout_id}")
        if "finance:approve" not in approver.scopes:
            raise PermissionError("approver lacks finance:approve scope")
        if payout.status != "pending_approval":
            return payout
        payout.status = "approved"
        self.metrics.inc("payouts_approved")
        self.audit.append(approver.subject, "payout.approve",
                          {"payout_id": payout_id})
        return payout

    def execute_payout(self, token: Token, payout_id: str) -> Payout:
        payout = self.payouts.get(payout_id)
        if payout is None:
            raise KeyError(f"unknown payout {payout_id}")
        if payout.status == "pending_approval":
            raise PermissionError("payout needs human approval first")
        if payout.status == "executed":
            return payout
        if payout.status not in ("created", "approved"):
            raise PermissionError(f"cannot execute payout in {payout.status}")
        payout.status = "executed"
        self.metrics.inc("payouts_executed")
        self.audit.append(token.subject, "payout.execute",
                          {"payout_id": payout_id,
                           "amount_minor": payout.amount_minor})
        return payout

    # -- evaluation ------------------------------------------------------
    def evaluate(self, token: Token,
                 golden: list[dict]) -> dict:
        """Score reconciliation against golden cases (ground truth)."""
        passed = 0
        for case in golden:
            outcome = self.run_reconciliation(token, case["ledger"],
                                              case["bank"])
            if (len(outcome.matches) == case["expected_matches"]
                    and len(outcome.unmatched_ledger)
                    == case["expected_unmatched_ledger"]):
                passed += 1
        return {"cases": len(golden), "passed": passed,
                "pass_rate": passed / len(golden) if golden else 1.0}
