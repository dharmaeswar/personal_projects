"""Tool-call parsing and validation.

Model text carries tool calls in fenced ```json blocks or <tool_call>
blocks. This module extracts them into typed ``ToolCall`` objects and
validates each one against a declared ``ToolSpec``: the tool must be
known, every required parameter must be present, and argument types must
match. A malformed block is reported as a parse error, never silently
accepted as a call.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)
_TOOL_CALL_TAG_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)

# JSON type names accepted in a ToolSpec, mapped to Python types.
_JSON_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


@dataclass(frozen=True)
class ToolCall:
    """One parsed tool call: tool name, arguments, and the raw JSON text."""

    name: str
    arguments: dict
    raw: str


@dataclass(frozen=True)
class ToolSpec:
    """The declared schema of one tool: its parameters and which are required."""

    name: str
    description: str = ""
    parameters: dict[str, str] = field(default_factory=dict)  # param -> JSON type name
    required: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        unknown = sorted(set(self.parameters.values()) - set(_JSON_TYPES))
        if unknown:
            raise ValueError(f"unknown JSON types in spec for {self.name!r}: {unknown}")
        missing = sorted(set(self.required) - set(self.parameters))
        if missing:
            raise ValueError(f"required params not declared for {self.name!r}: {missing}")


def _calls_from_json_text(text: str) -> list[ToolCall]:
    """Parse one JSON object (or a list of them) into ToolCall objects."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    calls: list[ToolCall] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("tool")
        arguments = item.get("arguments") or item.get("args") or {}
        if isinstance(name, str) and isinstance(arguments, dict):
            calls.append(ToolCall(name=name, arguments=arguments, raw=text.strip()))
    return calls


def parse_tool_calls(text: str) -> list[ToolCall]:
    """Extract every tool call from model text.

    Looks in fenced ```json blocks and <tool_call>...</tool_call> blocks,
    in document order. Blocks that are not valid tool-call JSON are
    skipped, not treated as calls.
    """
    calls: list[ToolCall] = []
    spans: list[tuple[int, str]] = []
    for match in _FENCED_JSON_RE.finditer(text):
        spans.append((match.start(), match.group(1)))
    for match in _TOOL_CALL_TAG_RE.finditer(text):
        spans.append((match.start(), match.group(1)))
    for _, block in sorted(spans):
        calls.extend(_calls_from_json_text(block))
    return calls


def validate_tool_call(call: ToolCall, specs: dict[str, ToolSpec]) -> list[str]:
    """Validate ``call`` against the declared tool specs. Returns error list.

    An empty list means the call is valid: known tool, all required
    parameters present, argument types matching the spec. Note ``bool`` is
    a subclass of ``int`` in Python, so a boolean is rejected where an
    integer is expected, and vice versa.
    """
    errors: list[str] = []
    spec = specs.get(call.name)
    if spec is None:
        return [f"unknown tool {call.name!r}"]
    for param in spec.required:
        if param not in call.arguments:
            errors.append(f"missing required parameter {param!r}")
    for param, value in call.arguments.items():
        expected_name = spec.parameters.get(param)
        if expected_name is None:
            errors.append(f"undeclared parameter {param!r}")
            continue
        expected = _JSON_TYPES[expected_name]
        if isinstance(value, bool) != (expected_name == "boolean"):
            errors.append(f"parameter {param!r} must be {expected_name}, got {type(value).__name__}")
        elif not isinstance(value, expected):
            errors.append(f"parameter {param!r} must be {expected_name}, got {type(value).__name__}")
    return errors
