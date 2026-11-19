"""Tool-call tracing with a deterministic latency/cost model.

A real agent harness needs to know, per call, what the agent asked for,
how long it took, and what it cost. Here latency and cost are simulated
with a fixed per-tool model (no network, no LLM API), so runs are fully
reproducible and the evals can assert on budgets.
"""

from __future__ import annotations

import time

# Simulated per-tool cost model: prompt+completion tokens and price.
# Values are made-up harness constants, not measured model pricing.
TOOL_COST_MODEL = {
    "lookup_invoice": {"tokens": 120, "latency_ms": 45},
    "lookup_po": {"tokens": 110, "latency_ms": 40},
    "approve_invoice": {"tokens": 90, "latency_ms": 60},
    "flag_invoice": {"tokens": 90, "latency_ms": 55},
    "lookup_customer": {"tokens": 100, "latency_ms": 40},
    "get_ticket": {"tokens": 130, "latency_ms": 50},
    "search_kb": {"tokens": 260, "latency_ms": 120},
    "resolve_ticket": {"tokens": 90, "latency_ms": 55},
    "escalate_ticket": {"tokens": 100, "latency_ms": 60},
}

PRICE_PER_1K_TOKENS_USD = 0.003


class ToolCall:
    def __init__(self, tool, args, status, latency_ms, cost_usd, error=None):
        self.tool = tool
        self.args = dict(args)
        self.status = status
        self.latency_ms = latency_ms
        self.cost_usd = cost_usd
        self.error = error

    def to_dict(self):
        return {"tool": self.tool, "args": self.args, "status": self.status,
                "latency_ms": self.latency_ms, "cost_usd": round(self.cost_usd, 6),
                "error": self.error}


class Tracer:
    """Collects one ToolCall per tool invocation and aggregates totals."""

    def __init__(self):
        self.calls = []
        self.started_at = time.time()

    def record(self, tool, args, status, error=None):
        model = TOOL_COST_MODEL.get(tool, {"tokens": 100, "latency_ms": 50})
        cost = model["tokens"] / 1000.0 * PRICE_PER_1K_TOKENS_USD
        call = ToolCall(tool, args, status, model["latency_ms"], cost, error)
        self.calls.append(call)
        return call

    def tool_names(self):
        return [c.tool for c in self.calls]

    def total_latency_ms(self):
        return sum(c.latency_ms for c in self.calls)

    def total_cost_usd(self):
        return round(sum(c.cost_usd for c in self.calls), 6)

    def errors(self):
        return [c for c in self.calls if c.status == "error"]

    def to_dict(self):
        return {"calls": [c.to_dict() for c in self.calls],
                "total_latency_ms": self.total_latency_ms(),
                "total_cost_usd": self.total_cost_usd(),
                "error_count": len(self.errors())}
