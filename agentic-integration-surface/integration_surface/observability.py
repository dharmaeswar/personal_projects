"""Structured logging, traces, and latency/failure metrics.

Every tool invocation produces one structured log line, one trace span, and
one metrics observation, so agent-driven traffic can be diagnosed from the
logs alone: which tool, which tenant, how long, what failed, and why.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Trace:
    """A single span covering one tool invocation."""

    trace_id: str
    tool: str
    started_at: float = field(default_factory=time.time)
    ended_at: float = 0.0
    status: str = "ok"  # ok | error | partial
    error_code: str = ""

    @property
    def latency_ms(self) -> float:
        end = self.ended_at or time.time()
        return round((end - self.started_at) * 1000, 3)

    def finish(self, status: str, error_code: str = "") -> None:
        self.ended_at = time.time()
        self.status = status
        self.error_code = error_code


class Metrics:
    """Per-tool call counts, errors, and latency (in-memory)."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self.errors: dict[str, int] = {}
        self.latencies_ms: dict[str, list[float]] = {}

    def observe(self, tool: str, latency_ms: float, status: str) -> None:
        self.calls[tool] = self.calls.get(tool, 0) + 1
        self.latencies_ms.setdefault(tool, []).append(latency_ms)
        if status != "ok":
            self.errors[tool] = self.errors.get(tool, 0) + 1

    def summary(self, tool: str) -> dict:
        lat = sorted(self.latencies_ms.get(tool, []))
        if not lat:
            return {"calls": 0, "errors": 0}
        return {
            "calls": self.calls.get(tool, 0),
            "errors": self.errors.get(tool, 0),
            "p50_ms": lat[len(lat) // 2],
            "p95_ms": lat[max(0, int(len(lat) * 0.95) - 1)],
            "max_ms": lat[-1],
        }

    def to_dict(self) -> dict:
        return {tool: self.summary(tool) for tool in self.calls}


class Observer:
    """Collects structured log lines, traces, and metrics for tool calls."""

    def __init__(self) -> None:
        self.logs: list[dict] = []
        self.traces: list[Trace] = []
        self.metrics = Metrics()

    def start_trace(self, tool: str) -> Trace:
        trace = Trace(trace_id=uuid.uuid4().hex[:16], tool=tool)
        self.traces.append(trace)
        return trace

    def log(self, level: str, tool: str, message: str, **fields: object) -> None:
        entry = {
            "level": level,
            "tool": tool,
            "message": message,
            "ts": round(time.time(), 3),
            **fields,
        }
        self.logs.append(entry)

    def finish(self, trace: Trace, result_status: str, **fields: object) -> None:
        trace.finish(result_status, str(fields.get("error_code", "")))
        self.metrics.observe(trace.tool, trace.latency_ms, result_status)
        self.log(
            "error" if result_status == "error" else "info",
            trace.tool,
            f"tool {trace.tool} finished: {result_status}",
            trace_id=trace.trace_id,
            latency_ms=trace.latency_ms,
            status=result_status,
            **fields,
        )

    def diagnostics(self, tool: str) -> dict:
        """Actionable diagnostics for one tool: recent failures and latency."""
        failures = [
            t for t in self.traces if t.tool == tool and t.status != "ok"
        ][-5:]
        return {
            "tool": tool,
            "metrics": self.metrics.summary(tool),
            "recent_failures": [
                {"trace_id": t.trace_id, "status": t.status, "error": t.error_code}
                for t in failures
            ],
            "recent_logs": [json.dumps(e) for e in self.logs[-5:]],
        }
