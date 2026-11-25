"""MCP-style tool server: the tool-integration protocol agents call.

Every tool declares a JSON input schema. Calls are validated against the
schema before dispatch, and every call is traced with latency and cost, so
the observability layer can say exactly what each agent did and what it
spent. The handlers here are deterministic stand-ins for real developer
tools (code search, test runner, PR opener); the schema, validation and
tracing are the real interface a coding-agent SDK would front.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

TYPE_CHECKS = {"string": str, "integer": int, "number": (int, float), "boolean": bool}


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, str]  # param name -> JSON type
    required: list[str]
    handler: Callable[[dict[str, Any]], Any]
    cost_per_call: float = 0.0


@dataclass
class TraceEntry:
    tool: str
    args: dict[str, Any]
    latency_ms: float
    cost: float
    ok: bool
    error: str = ""


class ToolServer:
    def __init__(self) -> None:
        self.tools: dict[str, Tool] = {}
        self.trace: list[TraceEntry] = []

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def call(self, name: str, args: dict[str, Any]) -> Any:
        """Validate args against the tool's schema, dispatch, and trace."""
        started = time.perf_counter()
        if name not in self.tools:
            entry = TraceEntry(name, args, 0.0, 0.0, False, f"unknown tool: {name}")
            self.trace.append(entry)
            raise ValueError(entry.error)
        tool = self.tools[name]
        error = self._validate(tool, args)
        if error:
            entry = TraceEntry(name, args, 0.0, 0.0, False, error)
            self.trace.append(entry)
            raise ValueError(error)
        try:
            result = tool.handler(dict(args))
        except Exception as exc:  # noqa: BLE001 - traced, not swallowed
            latency = (time.perf_counter() - started) * 1000
            self.trace.append(TraceEntry(name, args, latency, 0.0, False, str(exc)))
            raise
        latency = (time.perf_counter() - started) * 1000
        self.trace.append(TraceEntry(name, args, latency, tool.cost_per_call, True))
        return result

    @staticmethod
    def _validate(tool: Tool, args: dict[str, Any]) -> str:
        for param in tool.required:
            if param not in args:
                return f"missing required parameter: {param}"
        for param, value in args.items():
            expected = tool.parameters.get(param)
            if expected is None:
                return f"unexpected parameter: {param}"
            if not isinstance(value, TYPE_CHECKS[expected]):
                return f"parameter {param} must be {expected}"
            if expected == "integer" and isinstance(value, bool):
                return f"parameter {param} must be integer"
        return ""

    def totals(self) -> dict[str, Any]:
        calls = len(self.trace)
        return {
            "calls": calls,
            "failed_calls": sum(1 for t in self.trace if not t.ok),
            "total_latency_ms": round(sum(t.latency_ms for t in self.trace), 2),
            "total_cost": round(sum(t.cost for t in self.trace), 4),
            "calls_by_tool": {
                name: sum(1 for t in self.trace if t.tool == name)
                for name in sorted({t.tool for t in self.trace})
            },
        }
