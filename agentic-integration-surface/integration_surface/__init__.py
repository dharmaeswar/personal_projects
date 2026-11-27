"""Agentic Integration Surface.

An MCP-style integration layer that exposes legacy-application modernization
capabilities (schema analysis, relational-to-document transformation, migration
dry-run, migrated-data validation) as versioned, well-specified tools an AI
agent can discover, invoke, and orchestrate.

Every tool call carries a caller context (user, tenant, scopes) that is checked
at every boundary, every call is validated against a JSON-schema contract with
explicit error semantics (including partial success), and every call is observed
through structured logs, traces, and latency/failure metrics.

All data is synthetic and local. No network calls, no model calls, no
credentials. The "model" behind agent-driven calls is a seeded deterministic
stub so nondeterministic behaviour can be tested reproducibly.
"""

from .context import CallerContext, ContextError
from .contracts import (
    ContractError,
    PartialSuccess,
    ToolError,
    ToolResult,
    validate_call,
)
from .observability import Metrics, Observer, Trace
from .tools import Tool, ToolRegistry

__all__ = [
    "CallerContext",
    "ContextError",
    "ContractError",
    "Metrics",
    "Observer",
    "PartialSuccess",
    "Tool",
    "ToolError",
    "ToolRegistry",
    "ToolResult",
    "Trace",
    "validate_call",
]
