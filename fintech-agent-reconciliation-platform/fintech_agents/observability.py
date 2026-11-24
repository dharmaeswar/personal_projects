"""Observability — CloudWatch-shaped metrics and an audit log."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field


class Metrics:
    """Counters and latency samples, the way CloudWatch would hold them."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.latencies_ms: dict[str, list[float]] = {}

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + value

    def record_latency(self, name: str, ms: float) -> None:
        self.latencies_ms.setdefault(name, []).append(ms)

    def p95_ms(self, name: str) -> float:
        samples = sorted(self.latencies_ms.get(name, []))
        if not samples:
            return 0.0
        return samples[min(len(samples) - 1, int(0.95 * len(samples)))]


@dataclass
class AuditEntry:
    seq: int
    timestamp: int
    actor: str
    action: str
    detail: dict
    prev_hash: str
    entry_hash: str = ""


class AuditLog:
    """Append-only, hash-chained audit trail (tamper-evident)."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def append(self, actor: str, action: str, detail: dict,
               *, timestamp: int | None = None) -> AuditEntry:
        prev = self.entries[-1].entry_hash if self.entries else "GENESIS"
        entry = AuditEntry(
            seq=len(self.entries) + 1,
            timestamp=int(time.time()) if timestamp is None else timestamp,
            actor=actor, action=action, detail=detail, prev_hash=prev)
        body = json.dumps([entry.seq, entry.timestamp, entry.actor,
                           entry.action, entry.detail, entry.prev_hash],
                          sort_keys=True)
        entry.entry_hash = hashlib.sha256(body.encode()).hexdigest()
        self.entries.append(entry)
        return entry

    def verify(self) -> bool:
        prev = "GENESIS"
        for entry in self.entries:
            if entry.prev_hash != prev:
                return False
            body = json.dumps([entry.seq, entry.timestamp, entry.actor,
                               entry.action, entry.detail, entry.prev_hash],
                              sort_keys=True)
            if hashlib.sha256(body.encode()).hexdigest() != entry.entry_hash:
                return False
            prev = entry.entry_hash
        return True


# -- structured logging, tracing, AI cost tracking -------------------
# Added for the Finance AI Engineer shape: production observability
# means JSON logs that carry a trace, spans that time each step, and
# a ledger of model-token spend — the same three things the posting
# names (structured logging, tracing, alerting, AI cost tracking).

@dataclass
class Span:
    trace_id: str
    span_id: str
    name: str
    parent_span_id: str | None = None
    start_ms: float = 0.0
    end_ms: float | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.end_ms is None:
            return None
        return self.end_ms - self.start_ms


class Tracer:
    """Trace ids group spans; each span times one step of a run."""

    def __init__(self) -> None:
        self.spans: list[Span] = []
        self._counter = 0

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter:04d}"

    def start_span(self, name: str, *, trace_id: str | None = None,
                   parent: Span | None = None) -> Span:
        trace = trace_id or self._next_id("trace")
        span = Span(trace, self._next_id("span"), name,
                    parent_span_id=parent.span_id if parent else None,
                    start_ms=time.monotonic() * 1000)
        self.spans.append(span)
        return span

    def end_span(self, span: Span) -> Span:
        span.end_ms = time.monotonic() * 1000
        return span


class StructuredLogger:
    """JSON log lines, each carrying trace/span ids so a run can be
    followed end to end. Kept in memory; `lines` is the sink."""

    def __init__(self) -> None:
        self.lines: list[dict] = []

    def log(self, level: str, message: str, *,
            trace_id: str = "", span_id: str = "",
            **fields) -> dict:
        line = {"timestamp": int(time.time()), "level": level,
                "message": message, "trace_id": trace_id,
                "span_id": span_id, **fields}
        self.lines.append(line)
        return line


class CostTracker:
    """AI workload cost tracking: tokens in/out per model at a
    stated price per 1k tokens. Prices are inputs, not market data."""

    def __init__(self) -> None:
        self.usage: list[dict] = []

    def record(self, model: str, prompt_tokens: int,
               completion_tokens: int,
               price_per_1k_usd: float) -> dict:
        total = prompt_tokens + completion_tokens
        cost = round(total / 1000 * price_per_1k_usd, 6)
        entry = {"model": model, "prompt_tokens": prompt_tokens,
                 "completion_tokens": completion_tokens,
                 "total_tokens": total, "cost_usd": cost}
        self.usage.append(entry)
        return entry

    @property
    def total_cost_usd(self) -> float:
        return round(sum(u["cost_usd"] for u in self.usage), 6)

    @property
    def total_tokens(self) -> int:
        return sum(u["total_tokens"] for u in self.usage)
