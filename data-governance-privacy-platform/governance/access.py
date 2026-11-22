"""RBAC + purpose-based access evaluation (least privilege).

Every access request names a role, a purpose, a dataset and the columns
being read. The evaluator returns allow/deny with a reason, and whether
the read must be masked.

Rules (in evaluation order):

1. Unknown role -> deny.
2. Unknown dataset -> deny.
3. Unknown column -> deny.
4. Model training on a dataset under legal hold -> deny for every role
   (held data must not feed new models).
5. Role sensitivity ceiling: analyst and auditor may not read restricted
   columns at all; admin and data-engineer may.
6. Purpose restriction: ``support`` may not read restricted columns
   (support staff do not need account numbers / SSNs).
7. Auditors get masked reads only — they verify controls, they do not
   need raw PII.

Every decision is appended to an in-memory access-request log.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .catalog import Catalog
from .classify import CONFIDENTIAL, RESTRICTED, Sensitivity

ROLES = ("admin", "data-engineer", "analyst", "auditor")
PURPOSES = ("reporting", "model-training", "support", "audit", "operations")

# Highest sensitivity each role may read unmasked / at all.
ROLE_CEILING: Dict[str, Sensitivity] = {
    "admin": RESTRICTED,
    "data-engineer": RESTRICTED,
    "analyst": CONFIDENTIAL,
    "auditor": CONFIDENTIAL,
}

_SENSITIVITY_RANK = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}

# Purposes that may never touch restricted columns, whatever the role.
RESTRICTED_BLOCKED_PURPOSES = frozenset({"support"})


@dataclass(frozen=True)
class AccessRequest:
    role: str
    purpose: str
    dataset: str
    columns: List[str]


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str
    masked: bool = False  # True when the read is allowed but values must be masked


@dataclass
class AccessLogEntry:
    request: AccessRequest
    decision: AccessDecision


class AccessEvaluator:
    """Evaluates access requests against a catalog."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog
        self.log: List[AccessLogEntry] = []

    def evaluate(self, request: AccessRequest) -> AccessDecision:
        decision = self._decide(request)
        self.log.append(AccessLogEntry(request=request, decision=decision))
        return decision

    def _decide(self, request: AccessRequest) -> AccessDecision:
        if request.role not in ROLES:
            return AccessDecision(False, f"unknown role {request.role!r}")
        if request.purpose not in PURPOSES:
            return AccessDecision(False, f"unknown purpose {request.purpose!r}")
        try:
            dataset = self.catalog.get(request.dataset)
        except KeyError:
            return AccessDecision(False, f"unknown dataset {request.dataset!r}")

        if request.purpose == "model-training" and dataset.legal_hold:
            return AccessDecision(
                False,
                f"dataset {dataset.name!r} is under legal hold: model training is blocked",
            )

        ceiling = ROLE_CEILING[request.role]
        for col_name in request.columns:
            try:
                col = dataset.column(col_name)
            except KeyError:
                return AccessDecision(False, f"unknown column {col_name!r} in {dataset.name!r}")
            sensitivity = col.sensitivity or "internal"
            if _SENSITIVITY_RANK[sensitivity] > _SENSITIVITY_RANK[ceiling]:
                return AccessDecision(
                    False,
                    f"role {request.role!r} may not read {sensitivity} column {col_name!r}",
                )
            if sensitivity == RESTRICTED and request.purpose in RESTRICTED_BLOCKED_PURPOSES:
                return AccessDecision(
                    False,
                    f"purpose {request.purpose!r} may not read restricted column {col_name!r}",
                )

        if request.role == "auditor":
            return AccessDecision(True, "allowed with masking (auditor reads are masked only)",
                                  masked=True)
        return AccessDecision(True, "allowed")
