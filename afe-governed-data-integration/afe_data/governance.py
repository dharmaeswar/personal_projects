"""Governance: classification, masking, role-based access, and lineage.

Classification tags columns by sensitivity from name patterns and sampled
values. Masking never returns restricted values raw to non-privileged roles.
Access is role + purpose based, and every access decision is logged. Lineage
records, for every published row, the source, schema version, transform
step, and contract version that produced it — so any value can be traced
back to the write that produced it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

PII_PATTERNS = ("email", "phone", "ssn", "tax_id", "dob", "birth", "address", "account_no", "name")


def classify_column(column: str, sample_values: list[str]) -> str:
    """Return 'restricted', 'internal', or 'public' for a column."""
    lowered = column.lower()
    if any(p in lowered for p in PII_PATTERNS):
        return "restricted"
    for value in sample_values:
        text = str(value)
        if "@" in text and "." in text:
            return "restricted"
    return "internal"


def mask_value(value: str, method: str = "redact") -> str:
    if method == "redact":
        return "***"
    if method == "last4":
        return "****" + str(value)[-4:]
    if method == "hash":
        return hashlib.sha256(str(value).encode()).hexdigest()[:12]
    raise ValueError(f"unknown masking method {method!r}")


ROLES = ("pod-admin", "data-engineer", "analyst", "auditor")
# role -> sensitivity levels it may read raw
ROLE_CLEARANCE = {
    "pod-admin": {"public", "internal", "restricted"},
    "data-engineer": {"public", "internal"},
    "analyst": {"public", "internal"},
    "auditor": {"public", "internal", "restricted"},
}


@dataclass
class AccessLogEntry:
    role: str
    column: str
    sensitivity: str
    allowed: bool
    purpose: str


class AccessControl:
    """Role + purpose access decisions with an audit log."""

    def __init__(self):
        self.log: list[AccessLogEntry] = []

    def can_read(self, role: str, sensitivity: str, purpose: str) -> bool:
        allowed = sensitivity in ROLE_CLEARANCE.get(role, set())
        if purpose == "model-training" and sensitivity == "restricted":
            allowed = False  # restricted data never trains models directly
        self.log.append(AccessLogEntry(role, "", sensitivity, allowed, purpose))
        return allowed

    def read_row(self, role: str, row: dict, sensitivities: dict[str, str], purpose: str) -> dict:
        """Return the row with restricted columns masked for this role."""
        out = {}
        for column, value in row.items():
            level = sensitivities.get(column, "internal")
            if self.can_read(role, level, purpose):
                out[column] = value
            else:
                out[column] = mask_value(str(value), "redact") if value is not None else None
        return out


@dataclass
class LineageEntry:
    record_id: str
    source: str
    schema_version: str
    transform: str
    contract_version: str


class LineageLog:
    """Append-only lineage: every published row traces to its origin."""

    def __init__(self):
        self.entries: list[LineageEntry] = []

    def record(self, entry: LineageEntry) -> None:
        self.entries.append(entry)

    def trace(self, record_id: str) -> list[LineageEntry]:
        return [e for e in self.entries if e.record_id == record_id]
