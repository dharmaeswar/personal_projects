"""Rule-based PII / sensitivity classification.

Two signals are combined for each column:

1. Column-name patterns (e.g. a column called ``email`` or ``ssn``).
2. Sampled-value checks against the column's values (regexes for email,
   phone, SSN, account numbers and dates of birth).

The classifier returns both a sensitivity level and the name of the rule
that fired, so every classification is explainable in an audit trail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

# Sensitivity levels, least to most sensitive.
PUBLIC = "public"
INTERNAL = "internal"
CONFIDENTIAL = "confidential"
RESTRICTED = "restricted"

Sensitivity = str

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
_PHONE_RE = re.compile(r"^\+?1?[-.\s]?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}$")
_SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")
_ACCOUNT_RE = re.compile(r"^\d{10,17}$")
_DOB_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (name pattern, sensitivity, rule name, value check)
_NAME_RULES = [
    (re.compile(r"ssn|social.?security", re.I), RESTRICTED, "name:ssn"),
    (re.compile(r"password|secret|private.?key|api.?key", re.I), RESTRICTED, "name:credential"),
    (re.compile(r"email|e.?mail", re.I), CONFIDENTIAL, "name:email"),
    (re.compile(r"phone|mobile|cell", re.I), CONFIDENTIAL, "name:phone"),
    (re.compile(r"address|street|zip|postal", re.I), CONFIDENTIAL, "name:address"),
    (re.compile(r"dob|birth.?date|date.?of.?birth|born", re.I), CONFIDENTIAL, "name:dob"),
    (re.compile(r"account.?num|account.?id|routing", re.I), RESTRICTED, "name:account-number"),
    (re.compile(r"(^|_)name$|full.?name|first.?name|last.?name|customer.?name|member.?name", re.I),
     CONFIDENTIAL, "name:person-name"),
    (re.compile(r"salary|income|balance|credit.?score", re.I), CONFIDENTIAL, "name:financial"),
]


@dataclass(frozen=True)
class Classification:
    column: str
    sensitivity: Sensitivity
    rule: str  # rule that fired, e.g. "name:email" or "value:ssn"


def _value_rule(values: Sequence[object]) -> Optional[str]:
    """Check sampled values for PII shapes. Returns the rule name or None."""
    strings = [str(v) for v in values if v is not None and str(v) != ""]
    if not strings:
        return None
    sample = strings[:50]
    if all(_SSN_RE.match(v) for v in sample):
        return "value:ssn"
    if all(_EMAIL_RE.match(v) for v in sample):
        return "value:email"
    if all(_PHONE_RE.match(v) for v in sample):
        return "value:phone"
    if all(_ACCOUNT_RE.match(v) for v in sample):
        return "value:account-number"
    # NOTE: there is deliberately no value-based date-of-birth check here.
    # Any YYYY-MM-DD value (e.g. a transaction_date) matches a DOB shape,
    # so DOB detection is name-based only (see the "name:dob" rule).
    return None


_VALUE_SENSITIVITY = {
    "value:ssn": RESTRICTED,
    "value:account-number": RESTRICTED,
    "value:email": CONFIDENTIAL,
    "value:phone": CONFIDENTIAL,
}


def classify_column(name: str, sample_values: Sequence[object] = ()) -> Classification:
    """Classify one column from its name and (optionally) sampled values.

    Name rules win over value rules; if nothing fires the column is
    ``internal`` by default (never ``public`` — public needs an explicit
    owner decision, not a classifier guess).
    """
    for pattern, sensitivity, rule in _NAME_RULES:
        if pattern.search(name):
            return Classification(column=name, sensitivity=sensitivity, rule=rule)
    value_rule = _value_rule(sample_values)
    if value_rule is not None:
        return Classification(
            column=name,
            sensitivity=_VALUE_SENSITIVITY[value_rule],
            rule=value_rule,
        )
    return Classification(column=name, sensitivity=INTERNAL, rule="default:internal")


def classify_dataset(columns: Sequence[str],
                     rows: Sequence[Dict[str, object]]) -> Dict[str, Classification]:
    """Classify every column of a dataset using its rows as samples."""
    result: Dict[str, Classification] = {}
    for col in columns:
        samples = [row.get(col) for row in rows]
        result[col] = classify_column(col, samples)
    return result
