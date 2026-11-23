"""Lightweight observability hooks for the knowledge-ingestion service.

A small, dependency-free stand-in for the OpenTelemetry pattern the
enterprise AI platform uses: spans with start/end times and attributes,
named events, and counters. Everything is kept in memory and can be
exported as JSON lines (one event per line) for a log aggregator such as
Splunk. No network calls, no credentials, no production telemetry SDK.
"""

import json
import time


class Telemetry:
    """In-memory span/event/counter recorder."""

    def __init__(self):
        self.spans = []
        self.events = []
        self.counters = {}

    def start_span(self, name, attributes=None):
        """Open a span; return it so the caller can end it."""
        span = {
            "name": name,
            "attributes": dict(attributes or {}),
            "start_ms": time.monotonic() * 1000.0,
            "status": "open",
        }
        return span

    def end_span(self, span, status="ok"):
        """Close a span, recording its duration in milliseconds."""
        span["end_ms"] = time.monotonic() * 1000.0
        span["duration_ms"] = round(span["end_ms"] - span["start_ms"], 3)
        span["status"] = status
        self.spans.append(span)
        return span

    def record_event(self, name, attributes=None):
        """Record a single named event with attributes."""
        event = {"name": name, "attributes": dict(attributes or {})}
        self.events.append(event)
        return event

    def increment(self, name, value=1):
        """Add ``value`` to the named counter and return the new total."""
        self.counters[name] = self.counters.get(name, 0) + value
        return self.counters[name]

    def span_summary(self):
        """Per-span-name counts and total durations, for a status report."""
        summary = {}
        for span in self.spans:
            entry = summary.setdefault(
                span["name"], {"count": 0, "total_duration_ms": 0.0}
            )
            entry["count"] += 1
            entry["total_duration_ms"] = round(
                entry["total_duration_ms"] + span.get("duration_ms", 0.0), 3
            )
        return summary

    def to_jsonl(self):
        """All spans and events as JSON lines, one record per line."""
        records = [
            {"type": "span", **span} for span in self.spans
        ] + [{"type": "event", **event} for event in self.events]
        return "\n".join(json.dumps(record) for record in records) + "\n"
