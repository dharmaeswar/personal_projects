"""Tumbling-window aggregation over scored streaming events.

Modelled on Flink/Spark Structured Streaming windowed aggregation:
events are bucketed into fixed tumbling windows by event time, a
watermark tracks how far event time has advanced, and events that
arrive after the watermark has passed their window are counted as
late and dropped instead of silently corrupting a closed window.
All state is in memory; nothing here talks to a real stream engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WindowResult:
    """One closed tumbling window: counts per severity band."""

    window_start: float
    window_end: float
    counts: dict = field(default_factory=lambda: {"critical": 0, "watch": 0, "info": 0})
    events: int = 0

    def add(self, band_name: str) -> None:
        self.counts[band_name] = self.counts.get(band_name, 0) + 1
        self.events += 1


class TumblingWindows:
    """Fixed tumbling windows with a watermark and late-event handling."""

    def __init__(self, window_seconds: float = 60.0, allowed_lateness: float = 10.0):
        if window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if allowed_lateness < 0:
            raise ValueError("allowed_lateness must be >= 0")
        self.window_seconds = window_seconds
        self.allowed_lateness = allowed_lateness
        self._open: dict[float, WindowResult] = {}
        self._closed: list[WindowResult] = []
        self.watermark = float("-inf")
        self.late_dropped = 0
        self.on_time = 0

    def _window_start(self, event_time: float) -> float:
        return (event_time // self.window_seconds) * self.window_seconds

    def add(self, event_time: float, band_name: str) -> str:
        """Assign an event to its window.

        Returns "accepted" or "late" (dropped). Advancing the watermark
        closes every window that ends before it.
        """
        if event_time < 0:
            raise ValueError("event_time must be >= 0")
        if band_name not in ("critical", "watch", "info"):
            raise ValueError(f"unknown band: {band_name}")
        if event_time > self.watermark:
            self.watermark = event_time
        start = self._window_start(event_time)
        end = start + self.window_seconds
        if end <= self.watermark - self.allowed_lateness:
            self.late_dropped += 1
            return "late"
        window = self._open.setdefault(start, WindowResult(start, end))
        window.add(band_name)
        self.on_time += 1
        self._close_due_windows()
        return "accepted"

    def _close_due_windows(self) -> None:
        due = [s for s, w in self._open.items() if w.window_end <= self.watermark - self.allowed_lateness]
        for start in sorted(due):
            self._closed.append(self._open.pop(start))

    def close_all(self) -> list[WindowResult]:
        """Close every open window; returns all closed windows in order."""
        self._close_due_windows()
        for start in sorted(self._open):
            self._closed.append(self._open.pop(start))
        return sorted(self._closed, key=lambda w: w.window_start)

    @property
    def closed_windows(self) -> list[WindowResult]:
        return list(self._closed)

    @property
    def open_windows(self) -> list[WindowResult]:
        return sorted(self._open.values(), key=lambda w: w.window_start)
