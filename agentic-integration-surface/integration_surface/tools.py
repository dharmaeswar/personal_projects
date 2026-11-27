"""Tool registry: versioned tool definitions and dispatch.

Tools are the integration surface. Each tool has a stable name, a semantic
version, a JSON-schema input contract, required scopes, and a handler. Older
versions stay callable (backward compatibility): a v1 caller keeps working
after v2 ships, and the registry records which version was invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .context import CallerContext, ContextError
from .contracts import ContractError, ToolError, ToolResult, validate_call
from .observability import Observer

Handler = Callable[[CallerContext, dict], ToolResult]


@dataclass
class Tool:
    """One versioned integration surface."""

    name: str
    version: str  # e.g. "1.0", "2.0"
    description: str
    input_schema: dict
    required_scopes: tuple[str, ...] = ()
    handler: Handler | None = None
    deprecated: bool = False

    @property
    def key(self) -> str:
        return f"{self.name}@v{self.version.split('.')[0]}"


@dataclass
class ToolRegistry:
    """Holds every tool and dispatches validated, authorized, observed calls."""

    observer: Observer = field(default_factory=Observer)
    _tools: dict[str, Tool] = field(default_factory=dict)

    def register(self, tool: Tool) -> None:
        if tool.key in self._tools:
            raise ValueError(f"tool already registered: {tool.key}")
        self._tools[tool.key] = tool

    def list_tools(self) -> list[dict]:
        """Tool definitions as an agent would discover them (MCP-style)."""
        return [
            {
                "name": t.name,
                "version": t.version,
                "description": t.description,
                "inputSchema": t.input_schema,
                "deprecated": t.deprecated,
            }
            for t in sorted(self._tools.values(), key=lambda x: x.key)
        ]

    def get(self, name: str, version: str = "1.0") -> Tool:
        key = f"{name}@v{version.split('.')[0]}"
        tool = self._tools.get(key)
        if tool is None:
            raise ToolError("tool_not_found", f"no tool {key} is registered")
        return tool

    def invoke(
        self,
        name: str,
        args: dict,
        ctx: CallerContext,
        version: str = "1.0",
    ) -> ToolResult:
        """Validate, authorize, run, and observe one tool call."""
        trace = self.observer.start_trace(name)
        try:
            tool = self.get(name, version)
            if tool.deprecated:
                self.observer.log(
                    "warning", name, f"tool {tool.key} is deprecated",
                    trace_id=trace.trace_id,
                )
            validate_call(args, tool.input_schema)
            try:
                ctx.require_scopes(*tool.required_scopes)
            except ContextError as exc:
                raise ToolError("forbidden", str(exc)) from exc
            if tool.handler is None:
                raise ToolError("not_implemented", f"tool {name} has no handler")
            result = tool.handler(ctx.child(trace_id=trace.trace_id), args)
            status = "partial" if result.partial else ("ok" if result.ok else "error")
            self.observer.finish(
                trace, status, error_code=result.error.code if result.error else ""
            )
            return result
        except ToolError as exc:
            self.observer.finish(trace, "error", error_code=exc.code)
            return ToolResult(ok=False, error=exc)
        except Exception as exc:  # handler bug: never leak a stack trace to the agent
            self.observer.finish(trace, "error", error_code="internal_error")
            return ToolResult(
                ok=False,
                error=ToolError("internal_error", f"tool {name} failed unexpectedly: {exc}"),
            )
