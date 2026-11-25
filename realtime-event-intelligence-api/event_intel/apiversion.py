"""Versioned API contracts: schema evolution and backward compatibility.

The Zscaler Data & APIs role asks for production APIs with versioning,
auth, schema evolution, and backward-compatibility discipline. This
module implements the contract half:

- A contract pins a version and its fields (name -> type).
- `check_backward_compat` enforces additive-only evolution: a new
  version may add optional fields, but may not remove or rename a field
  or narrow a type — each violation is named, not silently allowed.
- `negotiate_version` picks the highest supported version at or below
  what the client asked for, the way content negotiation works.
- A deprecation registry records when a field is scheduled for removal,
  so clients get a removal version instead of a surprise.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ApiContract:
    version: str  # e.g. "v1", "v2"
    fields: dict[str, str]  # field name -> type name
    deprecated: dict[str, str] = field(default_factory=dict)
    # field name -> version it will be removed in


def check_backward_compat(old: ApiContract, new: ApiContract) -> dict:
    """Check a new contract version against the old one.

    Additive-only rule: every field in `old` must still exist in `new`
    with the same type. Added fields are fine. Returns violations (empty
    means compatible) and the added fields.
    """
    violations = []
    for name, type_name in old.fields.items():
        if name not in new.fields:
            violations.append(f"field removed: {name}")
        elif new.fields[name] != type_name:
            violations.append(
                f"field type changed: {name} "
                f"{type_name} -> {new.fields[name]}")
    added = sorted(set(new.fields) - set(old.fields))
    return {
        "compatible": not violations,
        "violations": violations,
        "added_fields": added,
    }


def negotiate_version(requested: str, supported: list[str]) -> str:
    """Pick the highest supported version at or below the requested one.

    Versions are "v<number>". Raises ValueError when no supported
    version satisfies the request (client too old) instead of silently
    serving the newest version.
    """
    def number(version: str) -> int:
        if not version.startswith("v") or not version[1:].isdigit():
            raise ValueError(f"bad version: {version!r}")
        return int(version[1:])

    wanted = number(requested)
    candidates = [v for v in supported if number(v) <= wanted]
    if not candidates:
        raise ValueError(
            f"no supported version at or below {requested}; "
            f"supported: {sorted(supported)}")
    return max(candidates, key=number)


def deprecate(contract: ApiContract, field_name: str,
              removal_version: str) -> ApiContract:
    """Record a field's planned removal. The field stays usable until then."""
    if field_name not in contract.fields:
        raise ValueError(f"unknown field: {field_name}")
    updated = ApiContract(
        version=contract.version,
        fields=dict(contract.fields),
        deprecated={**contract.deprecated,
                    field_name: removal_version},
    )
    return updated
