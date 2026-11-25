"""MCP-style tool server: the only way the agent touches data or models.

Every tool declares a JSON input schema. Arguments are validated against
the schema before dispatch, and every call is traced with latency and a
simulated cost, the way a model gateway would meter tool use. The tools
are deterministic stand-ins for the real services (a text-to-SQL model,
a sandboxed query runner); the schemas, tracing and validation are the
part this project demonstrates.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .sandbox import Sandbox, SandboxError
from .text_to_sql import translate, TranslationError

# Simulated per-call cost (USD) and latency (ms), as a model gateway
# would report. These are illustrative metering constants, not measured.
TOOL_COST = {
    "describe_dataset": 0.0001,
    "text_to_sql": 0.004,
    "run_query": 0.0005,
    "validate_result": 0.0002,
    "summarize": 0.002,
}

TOOL_SCHEMAS = {
    "describe_dataset": {
        "type": "object", "properties": {}, "required": [],
    },
    "text_to_sql": {
        "type": "object",
        "properties": {"question": {"type": "string"}},
        "required": ["question"],
    },
    "run_query": {
        "type": "object",
        "properties": {
            "sql": {"type": "string"},
            "row_limit": {"type": "integer"},
        },
        "required": ["sql"],
    },
    "validate_result": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "columns": {"type": "array"},
            "rows": {"type": "array"},
        },
        "required": ["question", "columns", "rows"],
    },
    "summarize": {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "columns": {"type": "array"},
            "rows": {"type": "array"},
        },
        "required": ["question", "columns", "rows"],
    },
}


class ToolError(Exception):
    """A tool call failed validation or execution."""


@dataclass
class ToolCall:
    name: str
    arguments: dict
    ok: bool
    result: object = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    error: str | None = None


@dataclass
class ToolServer:
    """Dispatches validated tool calls and traces every one."""

    sandbox: Sandbox
    trace: list[ToolCall] = field(default_factory=list)

    def call(self, name: str, arguments: dict) -> ToolCall:
        started = time.monotonic()
        try:
            result = self._dispatch(name, arguments)
        except (ToolError, SandboxError, TranslationError) as exc:
            call = ToolCall(name=name, arguments=arguments, ok=False,
                            latency_ms=(time.monotonic() - started) * 1000,
                            cost_usd=TOOL_COST.get(name, 0.0),
                            error=str(exc))
            self.trace.append(call)
            return call
        call = ToolCall(name=name, arguments=arguments, ok=True, result=result,
                        latency_ms=(time.monotonic() - started) * 1000,
                        cost_usd=TOOL_COST.get(name, 0.0))
        self.trace.append(call)
        return call

    def _validate(self, name: str, arguments: dict) -> None:
        schema = TOOL_SCHEMAS.get(name)
        if schema is None:
            raise ToolError(f"unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise ToolError("arguments must be an object")
        for key in schema["required"]:
            if key not in arguments:
                raise ToolError(f"missing required argument: {key}")
        for key, value in arguments.items():
            expected = schema["properties"].get(key, {}).get("type")
            if expected == "string" and not isinstance(value, str):
                raise ToolError(f"argument {key!r} must be a string")
            if expected == "integer" and not isinstance(value, int):
                raise ToolError(f"argument {key!r} must be an integer")
            if expected == "array" and not isinstance(value, list):
                raise ToolError(f"argument {key!r} must be an array")

    def _dispatch(self, name: str, arguments: dict):
        self._validate(name, arguments)
        if name == "describe_dataset":
            return self.sandbox.describe_dataset()
        if name == "text_to_sql":
            return {"sql": translate(arguments["question"])}
        if name == "run_query":
            return self.sandbox.run_query(
                arguments["sql"],
                row_limit=arguments.get("row_limit", 1000),
            )
        if name == "validate_result":
            return validate_result(arguments["question"],
                                   arguments["columns"], arguments["rows"])
        if name == "summarize":
            return {"summary": summarize(arguments["question"],
                                         arguments["columns"],
                                         arguments["rows"])}
        raise ToolError(f"unknown tool: {name}")

    def totals(self) -> dict:
        return {
            "calls": len(self.trace),
            "failed": sum(1 for c in self.trace if not c.ok),
            "latency_ms": round(sum(c.latency_ms for c in self.trace), 2),
            "cost_usd": round(sum(c.cost_usd for c in self.trace), 4),
        }


def validate_result(question: str, columns: list, rows: list) -> dict:
    """Result validation: empty results and missing columns are failures."""
    issues = []
    if not rows:
        issues.append("query returned no rows for a question that expects data")
    if not columns:
        issues.append("query returned no columns")
    return {"valid": not issues, "issues": issues,
            "row_count": len(rows), "columns": columns}


def summarize(question: str, columns: list, rows: list) -> str:
    """Plain-language summary grounded only in the returned rows.

    Every number in the summary comes from the rows, so the groundedness
    grader can check it mechanically. No outside facts are added.
    """
    if not rows:
        return f"No data was returned for: {question}"
    if len(columns) == 1:
        values = [r[0] for r in rows]
        if all(isinstance(v, (int, float)) for v in values):
            return (f"{question} The answer is {values[0]} "
                    f"({columns[0]}). Based on {len(rows)} row(s).")
        return (f"{question} The top result is {values[0]} "
                f"({columns[0]}). Based on {len(rows)} row(s).")
    first = rows[0]
    parts = ", ".join(f"{c} {v}" for c, v in zip(columns, first))
    return (f"{question} The top result is {parts}. "
            f"Based on {len(rows)} row(s).")
