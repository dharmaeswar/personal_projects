"""Input/output contracts: validation, error semantics, partial success.

Every tool declares a JSON-schema-style contract for its inputs and outputs.
Calls are validated before any handler runs; malformed calls fail fast with a
machine-readable error code. A call that processes a batch may succeed for
some items and fail for others — that is reported as an explicit partial
success, never silently swallowed and never reported as a full success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ToolError(Exception):
    """A tool call failed with a machine-readable error code."""

    def __init__(self, code: str, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ContractError(ToolError):
    """Input failed contract validation (malformed call)."""

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__("contract_violation", message, details=details)


@dataclass
class ToolResult:
    """The outcome of one tool call."""

    ok: bool
    data: Any = None
    error: ToolError | None = None
    # Per-item outcomes for batch calls; empty for single-item calls.
    item_results: list[dict] = field(default_factory=list)

    @property
    def partial(self) -> bool:
        """True when some batch items succeeded and some failed."""
        if not self.item_results:
            return False
        outcomes = {r["ok"] for r in self.item_results}
        return len(outcomes) > 1

    def to_dict(self) -> dict:
        out: dict[str, Any] = {"ok": self.ok}
        if self.data is not None:
            out["data"] = self.data
        if self.error is not None:
            out["error"] = {"code": self.error.code, "message": self.error.message}
            if self.error.details:
                out["error"]["details"] = self.error.details
        if self.item_results:
            out["items"] = self.item_results
            out["partial_success"] = self.partial
        return out


@dataclass
class PartialSuccess:
    """Helper that accumulates per-item outcomes for a batch call."""

    results: list[dict] = field(default_factory=list)

    def record(self, item_id: str, ok: bool, data: Any = None, error: str = "") -> None:
        entry: dict[str, Any] = {"id": item_id, "ok": ok}
        if data is not None:
            entry["data"] = data
        if error:
            entry["error"] = error
        self.results.append(entry)

    def as_result(self, data: Any = None) -> ToolResult:
        succeeded = sum(1 for r in self.results if r["ok"])
        failed = len(self.results) - succeeded
        if failed == 0:
            return ToolResult(ok=True, data=data, item_results=self.results)
        if succeeded == 0:
            return ToolResult(
                ok=False,
                data=data,
                error=ToolError(
                    "batch_failed",
                    f"all {failed} items failed",
                    details={"failed": failed},
                ),
                item_results=self.results,
            )
        return ToolResult(
            ok=False,
            data=data,
            error=ToolError(
                "partial_success",
                f"{succeeded} of {len(self.results)} items succeeded, "
                f"{failed} failed",
                details={"succeeded": succeeded, "failed": failed},
            ),
            item_results=self.results,
        )


def validate_call(args: dict, schema: dict) -> None:
    """Validate ``args`` against a small JSON-schema subset.

    Supports ``type`` (string/integer/number/boolean/array/object),
    ``required``, ``properties``, ``minimum``/``maximum``, ``minItems``,
    and ``enum``. Raises ContractError naming the offending field.
    """
    if not isinstance(args, dict):
        raise ContractError("arguments must be an object")
    for name in schema.get("required", []):
        if name not in args:
            raise ContractError(f"missing required field: {name}")
    for name, spec in schema.get("properties", {}).items():
        if name not in args:
            continue
        _validate_value(name, args[name], spec)
    for name in args:
        if name not in schema.get("properties", {}):
            raise ContractError(f"unknown field: {name}")


def _validate_value(name: str, value: Any, spec: dict) -> None:
    kind = spec.get("type")
    checks = {
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "boolean": lambda v: isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
    }
    if kind and not checks[kind](value):
        raise ContractError(f"field {name}: expected {kind}, got {type(value).__name__}")
    if "enum" in spec and value not in spec["enum"]:
        raise ContractError(f"field {name}: {value!r} not in {spec['enum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in spec and value < spec["minimum"]:
            raise ContractError(f"field {name}: {value} below minimum {spec['minimum']}")
        if "maximum" in spec and value > spec["maximum"]:
            raise ContractError(f"field {name}: {value} above maximum {spec['maximum']}")
    if isinstance(value, list) and "minItems" in spec and len(value) < spec["minItems"]:
        raise ContractError(f"field {name}: needs at least {spec['minItems']} items")
    if isinstance(value, dict) and "properties" in spec:
        validate_call(value, spec)
