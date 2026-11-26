"""Action model and validation.

A tenant Action is a named, versioned list of steps for one trigger.
Steps are data, not code: each step is a dict naming one allow-listed
operation (see sandbox.py). Anything outside the allow-list is rejected
at registration time, before the action can ever run.
"""

from dataclasses import dataclass, field

from .events import Trigger

ALLOWED_OPS = frozenset(
    {
        "set_claim",
        "deny",
        "allow",
        "redirect",
        "read_secret",
        "cache_get",
        "cache_put",
        "call_api",
        "log",
        "loop",
    }
)

# Per-step required keys, beyond "op".
STEP_FIELDS = {
    "set_claim": {"key", "value"},
    "deny": {"reason"},
    "allow": set(),
    "redirect": {"url"},
    "read_secret": {"name"},
    "cache_get": {"key"},
    "cache_put": {"key", "value"},
    "call_api": {"endpoint"},
    "log": {"message"},
    "loop": {"count", "steps"},
}

MAX_STEPS_PER_ACTION = 50
MAX_STEP_VALUE_CHARS = 2048


@dataclass
class Action:
    action_id: str
    tenant_id: str
    name: str
    trigger: Trigger
    steps: list
    version: int = 1
    deployed: bool = False

    def validate(self) -> None:
        if not self.action_id or not self.tenant_id or not self.name:
            raise ValueError("action_id, tenant_id and name are required")
        if not isinstance(self.trigger, Trigger):
            raise ValueError(f"unknown trigger {self.trigger!r}")
        if not self.steps or len(self.steps) > MAX_STEPS_PER_ACTION:
            raise ValueError(
                f"action needs 1-{MAX_STEPS_PER_ACTION} steps, "
                f"got {len(self.steps)}"
            )
        for i, step in enumerate(self.steps):
            if not isinstance(step, dict):
                raise ValueError(f"step {i} is not an object")
            op = step.get("op")
            if op not in ALLOWED_OPS:
                raise ValueError(f"step {i}: op {op!r} is not allowed")
            missing = STEP_FIELDS[op] - set(step)
            if missing:
                raise ValueError(f"step {i}: op {op!r} missing {sorted(missing)}")
            for key, value in step.items():
                if isinstance(value, str) and len(value) > MAX_STEP_VALUE_CHARS:
                    raise ValueError(f"step {i}: value for {key!r} exceeds limit")
            if op == "loop":
                count = step["count"]
                if not isinstance(count, int) or not 1 <= count <= 1000:
                    raise ValueError(f"step {i}: loop count must be 1-1000")
                substeps = step["steps"]
                if not isinstance(substeps, list) or not substeps:
                    raise ValueError(f"step {i}: loop needs non-empty steps")
                for j, sub in enumerate(substeps):
                    if not isinstance(sub, dict) or sub.get("op") not in ALLOWED_OPS:
                        raise ValueError(f"step {i}: loop sub-step {j} has bad op")
                    if sub.get("op") == "loop":
                        raise ValueError(f"step {i}: nested loops are not allowed")
