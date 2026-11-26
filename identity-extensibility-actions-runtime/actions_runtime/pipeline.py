"""Pipeline runner — executes a tenant's deployed actions for a trigger.

Actions for one trigger run in registration order against the same
event; later actions see claims set by earlier ones. On an action error
or timeout the trigger's policy decides the outcome:

- fail-closed triggers (pre-user-registration, pre-token-issuance):
  the whole flow is denied, so a broken action can never let a bad
  login or token through;
- fail-open triggers (post-login, post-change-password, ...): the error
  is logged and audited, the flow continues without that action.
"""

from dataclasses import dataclass, field

from .actions import Action
from .events import FAIL_CLOSED_TRIGGERS, AuthEvent, Trigger
from .observability import ActionMetrics, AuditLog
from .sandbox import Sandbox, SandboxResult


@dataclass
class PipelineResult:
    event: AuthEvent
    denied: bool = False
    deny_reason: str = ""
    redirect_url: str = ""
    action_results: list = field(default_factory=list)


class PipelineRunner:
    def __init__(self, sandbox: Sandbox, audit: AuditLog) -> None:
        self.sandbox = sandbox
        self.audit = audit
        self.metrics: dict[str, ActionMetrics] = {}

    def run(self, actions: list[Action], event: AuthEvent) -> PipelineResult:
        result = PipelineResult(event=event.clone())
        fail_closed = event.trigger in FAIL_CLOSED_TRIGGERS
        for action in actions:
            if not action.deployed or action.trigger != event.trigger:
                continue
            if action.tenant_id != event.tenant_id:
                continue
            outcome = self.sandbox.run(action, result.event)
            result.action_results.append(outcome)
            metrics = self.metrics.setdefault(action.action_id, ActionMetrics())
            metrics.record(
                outcome.simulated_ms,
                error=bool(outcome.error),
                denied=outcome.denied,
                timed_out=outcome.timed_out,
            )
            if outcome.error:
                self.audit.append(
                    event.tenant_id, action.action_id, event.trigger.value,
                    "error", outcome.error,
                )
                if fail_closed:
                    result.denied = True
                    result.deny_reason = f"action {action.action_id} failed: {outcome.error}"
                    return result
                continue
            if outcome.denied:
                self.audit.append(
                    event.tenant_id, action.action_id, event.trigger.value,
                    "deny", outcome.deny_reason,
                )
                result.denied = True
                result.deny_reason = outcome.deny_reason
                return result
            if outcome.redirect_url:
                result.redirect_url = outcome.redirect_url
            result.event.claims.update(outcome.claims)
            self.audit.append(
                event.tenant_id, action.action_id, event.trigger.value,
                "allow", f"{outcome.ops_used} ops, {outcome.simulated_ms} ms",
            )
        return result
