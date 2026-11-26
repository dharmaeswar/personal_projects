"""Sandboxed step interpreter — the untrusted-code execution boundary.

Tenant code never runs as native code. It runs as a list of validated
steps (see actions.py) executed by this interpreter, one op at a time,
against a single tenant's event. The interpreter enforces:

- an op budget: every step costs ops, and exceeding the budget aborts
  the action with a timeout (this is the latency budget for the local
  model; each op is charged a fixed simulated 1 ms so results are
  deterministic and testable without wall-clock flakiness);
- a claim-size cap, so one action cannot bloat tokens;
- tenant isolation: secrets and cache are always read under the
  action's own tenant_id, and a step naming another tenant is denied;
- no network, no file access, no eval/exec: the only outbound call is
  `call_api` against an in-process endpoint registry supplied by the
  platform, never the open internet.
"""

from dataclasses import dataclass, field

from .actions import Action
from .cache import TenantCache
from .events import MAX_CLAIM_VALUE_CHARS, AuthEvent
from .secrets import SecretStore, redact

SIMULATED_MS_PER_OP = 1
DEFAULT_OP_BUDGET = 100


@dataclass
class SandboxResult:
    action_id: str
    tenant_id: str
    denied: bool = False
    deny_reason: str = ""
    redirect_url: str = ""
    claims: dict = field(default_factory=dict)
    logs: list = field(default_factory=list)
    ops_used: int = 0
    simulated_ms: int = 0
    timed_out: bool = False
    error: str = ""


class SandboxTimeout(Exception):
    pass


class Sandbox:
    def __init__(
        self,
        secrets: SecretStore,
        cache: TenantCache,
        api_endpoints: dict | None = None,
        op_budget: int = DEFAULT_OP_BUDGET,
    ) -> None:
        self.secrets = secrets
        self.cache = cache
        self.api_endpoints = api_endpoints or {}
        self.op_budget = op_budget

    def _exec_step(self, step: dict, action: Action, working: AuthEvent,
                   result: SandboxResult) -> bool:
        """Execute one step. Returns True when the flow must stop
        (deny / allow / redirect). Raises on error or timeout."""
        op = step["op"]
        if op == "set_claim":
            value = str(step["value"])
            if len(value) > MAX_CLAIM_VALUE_CHARS:
                raise ValueError(
                    f"claim {step['key']!r} exceeds {MAX_CLAIM_VALUE_CHARS} chars"
                )
            working.claims[step["key"]] = value
        elif op == "deny":
            result.denied = True
            result.deny_reason = str(step["reason"])
            return True
        elif op == "allow":
            return True
        elif op == "redirect":
            result.redirect_url = str(step["url"])
            return True
        elif op == "read_secret":
            value = self.secrets.get(action.tenant_id, step["name"])
            result.logs.append(f"read secret {step['name']}={redact(value)}")
        elif op == "cache_get":
            value = self.cache.get(action.tenant_id, step["key"])
            result.logs.append(f"cache_get {step['key']}={'hit' if value is not None else 'miss'}")
        elif op == "cache_put":
            self.cache.put(action.tenant_id, step["key"], step["value"])
        elif op == "call_api":
            endpoint = step["endpoint"]
            if endpoint not in self.api_endpoints:
                raise ValueError(f"unknown api endpoint {endpoint!r}")
            outcome = self.api_endpoints[endpoint](working)
            result.logs.append(f"call_api {endpoint} -> {outcome}")
        elif op == "log":
            result.logs.append(str(step["message"]))
        else:  # pragma: no cover - validation rejects these first
            raise ValueError(f"op {op!r} is not allowed")
        return False

    def run(self, action: Action, event: AuthEvent) -> SandboxResult:
        result = SandboxResult(action_id=action.action_id, tenant_id=action.tenant_id)
        working = event.clone()
        ops = 0

        def charge() -> None:
            nonlocal ops
            ops += 1
            if ops > self.op_budget:
                raise SandboxTimeout(
                    f"op budget {self.op_budget} exceeded at step {ops}"
                )

        try:
            for step in action.steps:
                charge()
                if step["op"] == "loop":
                    for _ in range(step["count"]):
                        for sub in step["steps"]:
                            charge()
                            if self._exec_step(sub, action, working, result):
                                break
                        if result.denied or result.redirect_url:
                            break
                    if result.denied or result.redirect_url:
                        break
                    continue
                if self._exec_step(step, action, working, result):
                    break
        except SandboxTimeout as exc:
            result.timed_out = True
            result.error = str(exc)
        except Exception as exc:  # noqa: BLE001 - surfaced to the pipeline
            result.error = str(exc)
        result.ops_used = ops
        result.simulated_ms = ops * SIMULATED_MS_PER_OP
        result.claims = working.claims
        return result
