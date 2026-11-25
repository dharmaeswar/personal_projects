"""PII governance: classification, masking and role-based access.

Classification is rule-based: column-name patterns plus sampled-value
checks (email, phone, SSN, person name, date of birth). Masking is
deterministic per method (redact, last-4, SHA-256 hash). Access is
role-based: analysts never see restricted columns, auditors get a
read-only view with an access log, engineers see masked values only.
"""

from __future__ import annotations

import hashlib
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")
SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")

# column-name patterns -> sensitivity class
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(email|e_mail)", re.I), "email"),
    (re.compile(r"(phone|mobile|tel)", re.I), "phone"),
    (re.compile(r"(ssn|social_security)", re.I), "ssn"),
    (re.compile(r"(dob|birth_date|date_of_birth)", re.I), "dob"),
    (re.compile(r"(name|full_name|first_name|last_name)", re.I), "name"),
    (re.compile(r"(address|street|zip|postal)", re.I), "address"),
]

RESTRICTED = {"email", "phone", "ssn", "dob"}


def classify_column(column: str, sample_values: list[str] | None = None) -> str:
    """Return the sensitivity class of a column, or 'none'."""
    for pattern, cls in _PATTERNS:
        if pattern.search(column):
            return cls
    # Value-based fallback when the name gives nothing away.
    for value in (sample_values or []):
        v = str(value).strip()
        if EMAIL_RE.match(v):
            return "email"
        if SSN_RE.match(v):
            return "ssn"
        if PHONE_RE.match(v):
            return "phone"
    return "none"


def mask_value(value: str, sensitivity: str, method: str = "redact") -> str:
    """Mask one value. Methods: redact, last4, hash. Non-sensitive values pass through."""
    if sensitivity == "none":
        return value
    if method == "redact":
        return "[REDACTED]"
    if method == "last4":
        digits = re.sub(r"\D", "", value)
        return f"***-{digits[-4:]}" if len(digits) >= 4 else "[REDACTED]"
    if method == "hash":
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    raise ValueError(f"unknown masking method: {method}")


class AccessPolicy:
    """Role-based access over dataset columns.

    Roles: ``engineer`` (masked restricted columns), ``analyst`` (no
    restricted columns at all), ``auditor`` (masked restricted columns +
    every access logged). Unknown roles get nothing restricted.
    """

    def __init__(self, column_classes: dict[str, str]):
        self.column_classes = dict(column_classes)
        self.access_log: list[dict] = []

    def visible_columns(self, role: str) -> list[str]:
        visible: list[str] = []
        for column, cls in self.column_classes.items():
            if cls in RESTRICTED and role == "analyst":
                continue
            visible.append(column)
        return visible

    def project_row(self, row: dict, role: str, mask_method: str = "redact") -> dict:
        """Return the row as ``role`` may see it, masking restricted values."""
        out: dict = {}
        for column in self.visible_columns(role):
            value = row.get(column)
            cls = self.column_classes.get(column, "none")
            if cls in RESTRICTED and role in ("engineer", "auditor"):
                out[column] = mask_value(str(value), cls, mask_method) if value is not None else None
            else:
                out[column] = value
        if role == "auditor":
            self.access_log.append({"role": role, "columns": sorted(out), "row_keys": sorted(str(k) for k in row.keys())})
        return out
