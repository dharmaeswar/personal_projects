"""JSON contract validation for API responses (stdlib only).

A contract is a plain dict describing the shape a payload must have:

- {"type": "object", "required": ["id", "name"],
   "properties": {"id": {"type": "integer", "min": 1},
                  "name": {"type": "string", "min_length": 1}}}
- {"type": "array", "items": {...contract for each element...},
   "min_length": 1}
- {"type": "number", "min": 0} / {"type": "string", "enum": ["BUY", "SELL"]}
- {"type": "string", "pattern": "^[A-Z]+$"} (regex, stdlib ``re``)

``validate(payload, contract)`` returns a list of violation strings;
an empty list means the payload satisfies the contract. It never raises
on a malformed payload — every mismatch is reported as a violation, so
a failing contract check reads as a test failure, not an error.
"""
import re

_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
}


def validate(payload, contract, path="$"):
    """Validate ``payload`` against ``contract``. Returns [violations]."""
    violations = []
    expected = contract.get("type")
    if expected:
        py_type = _TYPES[expected]
        # bool is a subclass of int: an integer contract must reject bools.
        if expected == "integer" and isinstance(payload, bool):
            violations.append(f"{path}: expected integer, got boolean")
            return violations
        if expected == "number" and isinstance(payload, bool):
            violations.append(f"{path}: expected number, got boolean")
            return violations
        if not isinstance(payload, py_type):
            violations.append(
                f"{path}: expected {expected}, got "
                f"{type(payload).__name__}")
            return violations
    if expected == "object":
        for key in contract.get("required", ()):
            if key not in payload:
                violations.append(f"{path}: missing required key '{key}'")
        for key, sub in contract.get("properties", {}).items():
            if key in payload:
                violations.extend(validate(payload[key], sub, f"{path}.{key}"))
    elif expected == "array":
        if "min_length" in contract and len(payload) < contract["min_length"]:
            violations.append(
                f"{path}: length {len(payload)} below minimum "
                f"{contract['min_length']}")
        if "max_length" in contract and len(payload) > contract["max_length"]:
            violations.append(
                f"{path}: length {len(payload)} above maximum "
                f"{contract['max_length']}")
        items = contract.get("items")
        if items is not None:
            for i, item in enumerate(payload):
                violations.extend(validate(item, items, f"{path}[{i}]"))
    elif expected == "string":
        if "min_length" in contract and len(payload) < contract["min_length"]:
            violations.append(
                f"{path}: length {len(payload)} below minimum "
                f"{contract['min_length']}")
        if "max_length" in contract and len(payload) > contract["max_length"]:
            violations.append(
                f"{path}: length {len(payload)} above maximum "
                f"{contract['max_length']}")
        if "pattern" in contract and not re.search(contract["pattern"], payload):
            violations.append(
                f"{path}: {payload!r} does not match "
                f"{contract['pattern']!r}")
    if expected in ("number", "integer"):
        if "min" in contract and payload < contract["min"]:
            violations.append(
                f"{path}: {payload} below minimum {contract['min']}")
        if "max" in contract and payload > contract["max"]:
            violations.append(
                f"{path}: {payload} above maximum {contract['max']}")
    if "enum" in contract and payload not in contract["enum"]:
        violations.append(
            f"{path}: {payload!r} not in {contract['enum']}")
    return violations


def check(payload, contract):
    """True when ``payload`` satisfies ``contract`` (no violations)."""
    return validate(payload, contract) == []
