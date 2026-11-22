"""Masking policies for sensitive values.

Four masking modes:

- ``redact`` — replace the whole value with ``[REDACTED]``.
- ``partial`` — show only the last 4 characters, mask the rest with ``*``.
- ``hash`` — deterministic SHA-256 hex digest (same input + salt always
  yields the same output, so joins on hashed keys still work).
- ``tokenize`` — replace with a stable synthetic token (``TOK-000123``);
  the same input always maps to the same token within one run.

``mask_value`` applies the policy a column's classification and the
requesting role call for. Restricted columns are NEVER returned raw to
non-privileged roles — there is no code path that hands them out.
"""

from __future__ import annotations

import hashlib
from typing import Dict, Optional

from .classify import CONFIDENTIAL, PUBLIC, RESTRICTED, Sensitivity

# Roles allowed to see restricted columns unmasked.
PRIVILEGED_ROLES = frozenset({"admin", "data-engineer"})

DEFAULT_SALT = "data-governance-demo-salt"


def redact(value: object) -> str:
    return "[REDACTED]"


def partial_mask(value: object, visible: int = 4) -> str:
    """Show only the last ``visible`` characters; mask the rest with ``*``.

    Values shorter than ``visible`` are fully masked.
    """
    text = str(value)
    if len(text) <= visible:
        return "*" * len(text)
    return "*" * (len(text) - visible) + text[-visible:]


def deterministic_hash(value: object, salt: str = DEFAULT_SALT) -> str:
    """SHA-256 hex digest of ``salt + value`` — deterministic by design."""
    digest = hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()
    return digest


def tokenize(value: object, token_map: Optional[Dict[str, str]] = None) -> str:
    """Map a value to a stable synthetic token.

    The mapping is deterministic within a process: the same input always
    returns the same token. A caller-supplied ``token_map`` lets the
    mapping survive across calls; otherwise a fresh per-call map is used.
    """
    mapping: Dict[str, str] = token_map if token_map is not None else {}
    key = str(value)
    if key not in mapping:
        mapping[key] = f"TOK-{len(mapping) + 1:06d}"
    return mapping[key]


def mask_value(value: object, sensitivity: Sensitivity, role: str,
               token_map: Optional[Dict[str, str]] = None) -> object:
    """Return the value as ``role`` is allowed to see it.

    - public: returned as-is.
    - internal: returned as-is (internal data is visible to all staff roles).
    - confidential: privileged roles see it raw; everyone else gets a
      partial mask.
    - restricted: privileged roles see it raw; everyone else gets a
      deterministic hash (never the raw value, never a reversible mask).
    """
    if sensitivity in (PUBLIC, "internal"):
        return value
    if role in PRIVILEGED_ROLES:
        return value
    if sensitivity == CONFIDENTIAL:
        return partial_mask(value)
    if sensitivity == RESTRICTED:
        return deterministic_hash(value)
    return redact(value)
