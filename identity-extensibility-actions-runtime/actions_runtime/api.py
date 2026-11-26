"""REST-style service layer over the runtime.

This is the API surface a control plane would expose: create tenants,
register and deploy actions, store secrets, and invoke a trigger for a
login/token event. It returns plain dicts shaped like JSON responses so
the demo and tests exercise the same contract a real HTTP layer would
serve (REST today; the same handlers map onto gRPC methods). Mutating
calls accept an idempotency key: a retried register/deploy with the same
key returns the original response instead of creating a duplicate.
"""

from .actions import Action
from .cache import TenantCache
from .events import AuthEvent, Trigger
from .observability import AuditLog
from .pipeline import PipelineResult, PipelineRunner
from .sandbox import Sandbox
from .secrets import SecretStore
from .tenancy import Tenant, TenantRegistry


class ActionsService:
    def __init__(self, op_budget: int = 100) -> None:
        self.tenants = TenantRegistry()
        self.secrets = SecretStore()
        self.cache = TenantCache()
        self.audit = AuditLog()
        self.sandbox = Sandbox(self.secrets, self.cache, op_budget=op_budget)
        self.runner = PipelineRunner(self.sandbox, self.audit)
        self._actions: dict[str, Action] = {}
        self._idempotency: dict[str, dict] = {}

    # -- tenants ---------------------------------------------------------
    def create_tenant(self, tenant_id: str, name: str) -> dict:
        tenant = self.tenants.create(Tenant(tenant_id=tenant_id, name=name))
        return {"tenant_id": tenant.tenant_id, "name": tenant.name}

    # -- secrets ---------------------------------------------------------
    def put_secret(self, tenant_id: str, name: str, value: str) -> dict:
        tenant = self.tenants.get(tenant_id)
        if self.secrets.count(tenant_id) >= tenant.max_secrets and not self.secrets.has(tenant_id, name):
            raise ValueError(f"tenant {tenant_id!r} reached its secret limit")
        fingerprint = self.secrets.put(tenant_id, name, value)
        return {"tenant_id": tenant_id, "name": name, "fingerprint": fingerprint}

    # -- actions ---------------------------------------------------------
    def register_action(self, action: Action, idempotency_key: str = "") -> dict:
        if idempotency_key and idempotency_key in self._idempotency:
            return dict(self._idempotency[idempotency_key])
        tenant = self.tenants.get(action.tenant_id)
        action.validate()
        owned = [a for a in self._actions.values() if a.tenant_id == action.tenant_id]
        if len(owned) >= tenant.max_actions and action.action_id not in self._actions:
            raise ValueError(f"tenant {tenant.tenant_id!r} reached its action limit")
        if action.action_id in self._actions:
            existing = self._actions[action.action_id]
            if existing.tenant_id != action.tenant_id:
                raise PermissionError("action id belongs to another tenant")
            action.version = existing.version + 1
        self._actions[action.action_id] = action
        response = {
            "action_id": action.action_id,
            "tenant_id": action.tenant_id,
            "trigger": action.trigger.value,
            "version": action.version,
            "deployed": action.deployed,
        }
        if idempotency_key:
            self._idempotency[idempotency_key] = dict(response)
        return response

    def deploy_action(self, tenant_id: str, action_id: str) -> dict:
        action = self._actions.get(action_id)
        if action is None or action.tenant_id != tenant_id:
            raise ValueError(f"action {action_id!r} not found for tenant {tenant_id!r}")
        action.deployed = True
        return {"action_id": action_id, "deployed": True, "version": action.version}

    def list_actions(self, tenant_id: str, trigger: Trigger | None = None) -> list[dict]:
        self.tenants.get(tenant_id)
        out = []
        for action in self._actions.values():
            if action.tenant_id != tenant_id:
                continue
            if trigger is not None and action.trigger != trigger:
                continue
            out.append({"action_id": action.action_id, "trigger": action.trigger.value,
                        "version": action.version, "deployed": action.deployed})
        return out

    # -- invocation ------------------------------------------------------
    def invoke(self, event: AuthEvent) -> PipelineResult:
        self.tenants.get(event.tenant_id)
        actions = [a for a in self._actions.values() if a.tenant_id == event.tenant_id]
        return self.runner.run(actions, event)

    def health(self) -> dict:
        return {
            "status": "ok",
            "tenants": len(self.tenants._tenants),
            "actions": len(self._actions),
            "audit_entries": len(self.audit.entries),
            "audit_chain_valid": self.audit.verify_chain(),
        }
