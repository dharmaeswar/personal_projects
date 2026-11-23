"""Least-privilege policy engine: role -> allowed actions/resources.

A policy maps each role to the (action, resource-pattern) pairs it may
perform. Resource patterns use ``fnmatch`` globbing, so a role can be
scoped to one environment (``env:prod:*``) or one service
(``service:checkout``) without a second mechanism. Anything not
explicitly allowed is denied -- there is no default-allow path.
"""

from __future__ import annotations

import fnmatch

# Default policy for a DevOps-agent fleet. Roles are deliberately narrow:
# an operator can deploy, a reviewer can only read and approve, and only
# the admin role can touch secrets or delete resources.
DEFAULT_POLICY: dict[str, list[tuple[str, str]]] = {
    "deployer": [
        ("deploy", "service:*"),
        ("restart", "service:*"),
        ("read", "service:*"),
        ("read", "logs:*"),
    ],
    "operator": [
        ("read", "service:*"),
        ("read", "logs:*"),
        ("restart", "service:web-*"),
    ],
    "reviewer": [
        ("read", "service:*"),
        ("read", "logs:*"),
        ("approve", "deploy:*"),
    ],
    "admin": [
        ("*", "*"),
    ],
}


class PolicyEngine:
    def __init__(self, policy: dict[str, list[tuple[str, str]]] | None = None):
        self._policy = policy if policy is not None else DEFAULT_POLICY

    def allowed(self, role: str, action: str, resource: str) -> bool:
        """True only when the role explicitly allows this action/resource."""
        for allowed_action, pattern in self._policy.get(role, []):
            action_ok = allowed_action == "*" or allowed_action == action
            if action_ok and fnmatch.fnmatchcase(resource, pattern):
                return True
        return False

    def allowed_scopes(self, role: str) -> list[str]:
        return [f"{a}:{r}" for a, r in self._policy.get(role, [])]

    def roles(self) -> list[str]:
        return sorted(self._policy)
