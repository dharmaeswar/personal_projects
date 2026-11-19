"""Agentic rollout workflows with approval gates and an audit trail.

The agent plans a rollout as a sequence of steps. Low-risk steps are
auto-approved; medium- and high-risk steps need a human approval before
they run. Every decision — plan, approval, denial, guardrail failure,
rollback — is written to an append-only audit log with the actor and the
reason, so any rollout can be replayed and explained afterwards.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from .policies import evaluate_service
from .services import Service


@dataclass
class RolloutStep:
    name: str
    action: str
    risk: str  # low | medium | high
    requires_approval: bool = False


@dataclass
class AuditEntry:
    timestamp: str
    actor: str
    service: str
    action: str
    decision: str
    reason: str

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "actor": self.actor,
            "service": self.service,
            "action": self.action,
            "decision": self.decision,
            "reason": self.reason,
        }


class AuditLog:
    """Append-only log of every rollout decision."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, actor: str, service: str, action: str,
               decision: str, reason: str) -> AuditEntry:
        entry = AuditEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor=actor,
            service=service,
            action=action,
            decision=decision,
            reason=reason,
        )
        self._entries.append(entry)
        return entry

    def list(self, service: str | None = None,
             limit: int | None = None) -> list[AuditEntry]:
        out = [e for e in self._entries
               if service is None or e.service == service]
        if limit is not None:
            out = out[-limit:]
        return out

    def __len__(self) -> int:
        return len(self._entries)


def _risk_for(step_name: str, service: Service) -> str:
    if step_name == "validate-template":
        return "low"
    if step_name == "canary-5":
        return "low"
    if step_name == "canary-25":
        return "medium"
    if step_name == "canary-50":
        return "medium"
    if step_name == "full-rollout":
        return "high" if service.criticality == "critical" else "medium"
    if step_name == "verify-slos":
        return "low"
    return "medium"


class AgentWorkflow:
    """Plans and executes agent-driven rollouts under guardrails."""

    STEP_NAMES = ("validate-template", "canary-5", "canary-25",
                  "canary-50", "full-rollout", "verify-slos")

    STEP_ACTIONS = {
        "validate-template": "Run all deployment guardrails over the template",
        "canary-5": "Shift 5% of traffic to the new version",
        "canary-25": "Shift 25% of traffic to the new version",
        "canary-50": "Shift 50% of traffic to the new version",
        "full-rollout": "Shift 100% of traffic to the new version",
        "verify-slos": "Check availability and latency against SLO targets",
    }

    def __init__(self, audit_log: AuditLog | None = None) -> None:
        self.audit_log = audit_log if audit_log is not None else AuditLog()

    def plan_rollout(self, service: Service) -> list[RolloutStep]:
        """Build the step plan for a service, with approval gates."""
        steps = []
        for name in self.STEP_NAMES:
            risk = _risk_for(name, service)
            steps.append(RolloutStep(
                name=name,
                action=self.STEP_ACTIONS[name],
                risk=risk,
                requires_approval=risk in ("medium", "high"),
            ))
        self.audit_log.record(
            "agent", service.name, "plan-rollout", "planned",
            f"planned {len(steps)} steps for {service.criticality} service",
        )
        return steps

    def execute(self, service: Service, steps: list[RolloutStep],
                approvals: dict[str, bool] | None = None,
                approver: str = "human:owner") -> dict:
        """Run the plan in order; stop at the first failure or denial.

        approvals maps step name -> True (approved) / False (denied).
        A step that requires approval and has no entry is treated as
        denied, so nothing risky runs without an explicit human yes.
        Returns a result dict with per-step outcomes and the final state.
        """
        approvals = approvals or {}
        service.status = "deploying"
        outcomes: list[dict] = []

        guardrail_failures = [f for f in evaluate_service(service)
                              if not f.passed]
        if guardrail_failures:
            reason = ("guardrails failed: "
                      + ", ".join(f.guardrail for f in guardrail_failures))
            self.audit_log.record("agent", service.name, "validate-template",
                                  "blocked", reason)
            service.status = "registered"
            return {
                "service": service.name,
                "success": False,
                "blocked_at": "validate-template",
                "reason": reason,
                "steps": [],
            }

        for step in steps:
            if step.name == "validate-template":
                self.audit_log.record(
                    "agent", service.name, step.name, "passed",
                    "all guardrails passed")
                outcomes.append({"step": step.name, "outcome": "passed"})
                continue
            if step.requires_approval:
                approved = approvals.get(step.name, False)
                self.audit_log.record(
                    approver if approved else approver,
                    service.name, step.name,
                    "approved" if approved else "denied",
                    f"{step.risk}-risk step "
                    f"{'approved by human' if approved else 'no approval given'}",
                )
                if not approved:
                    outcomes.append({"step": step.name, "outcome": "denied"})
                    if service.auto_rollback and service.rollback_version:
                        self.audit_log.record(
                            "agent", service.name, "rollback", "executed",
                            f"rolled back to {service.rollback_version} "
                            "after denied approval")
                        service.status = "rolled-back"
                    else:
                        service.status = "registered"
                    return {
                        "service": service.name,
                        "success": False,
                        "blocked_at": step.name,
                        "reason": f"approval denied for {step.name}",
                        "steps": outcomes,
                    }
            else:
                self.audit_log.record(
                    "agent", service.name, step.name, "auto-approved",
                    f"{step.risk}-risk step auto-approved under policy")
            outcomes.append({"step": step.name, "outcome": "completed"})

        service.status = "live"
        self.audit_log.record("agent", service.name, "rollout", "completed",
                              "all steps completed; service live")
        return {
            "service": service.name,
            "success": True,
            "blocked_at": None,
            "reason": "all steps completed",
            "steps": outcomes,
        }
