"""Real-time agent behavior monitor.

Watches the stream of tool calls in one agent session and flags
anomalous behavior: call bursts, repeated failures, retries of a denied
sensitive tool, and read-then-export sequences that look like data
exfiltration. Thresholds are fixed constants; detection is a pure
function of the recorded call history.
"""
from dataclasses import dataclass

BURST_WINDOW_SECONDS = 60
BURST_MAX_CALLS = 5
FAILURE_STREAK = 3


@dataclass
class Anomaly:
    kind: str
    detail: str
    severity: str


class SessionMonitor:
    def __init__(self):
        self.events = []  # (timestamp, tool, allowed, reason)

    def record(self, timestamp, tool, allowed, reason=""):
        self.events.append((timestamp, tool, allowed, reason))

    def anomalies(self):
        found = []
        found += self._burst()
        found += self._failure_streak()
        found += self._denied_retry()
        found += self._read_then_export()
        return found

    def _burst(self):
        for i, (ts, _, _, _) in enumerate(self.events):
            window = [e for e in self.events
                      if ts - BURST_WINDOW_SECONDS <= e[0] <= ts]
            if len(window) > BURST_MAX_CALLS:
                return [Anomaly("call-burst",
                                f"{len(window)} tool calls within "
                                f"{BURST_WINDOW_SECONDS}s ending at t={ts}",
                                "medium")]
        return []

    def _failure_streak(self):
        streak = 0
        for _, _, allowed, _ in self.events:
            streak = streak + 1 if not allowed else 0
            if streak >= FAILURE_STREAK:
                return [Anomaly("failure-streak",
                                f"{streak} consecutive denied tool calls",
                                "medium")]
        return []

    def _denied_retry(self):
        denied_sensitive = set()
        for _, tool, allowed, reason in self.events:
            if not allowed and tool in ("delete_record", "export_data",
                                        "refund_customer", "send_email"):
                denied_sensitive.add(tool)
            if allowed and tool in denied_sensitive:
                return [Anomaly("denied-sensitive-retry",
                                f"sensitive tool {tool} succeeded after denial",
                                "high")]
        return []

    def _read_then_export(self):
        saw_read = False
        for _, tool, allowed, _ in self.events:
            if allowed and tool in ("lookup_customer", "lookup_invoice"):
                saw_read = True
            if allowed and tool == "export_data" and saw_read:
                return [Anomaly("read-then-export",
                                "export_data called after reading customer "
                                "records in the same session",
                                "high")]
        return []
