"""Fast alerts on failed surface checks.

An :class:`AlertSink` emits one alert record per violation *as the check
fails* -- it is wired into :func:`vol_surface_checker.checks.run_all_checks`
through its ``on_violation`` callback -- so a broken surface is surfaced to
the desk immediately instead of waiting for a batch report.

Each alert is a JSON object on one line (JSON Lines), written to the alert
stream (a file and/or the console), e.g.::

    {"alert": "surface_check_failed", "check": "calendar_arbitrage",
     "expiry": 1.0, "strike": 100.0, "severity": "high",
     "detail": "total variance falls from ...", "emitted_at": "..."}
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from .checks import Violation


class AlertSink:
    """Collects and emits alert records for failed checks.

    Parameters
    ----------
    stream : file-like, optional
        Console-style stream to echo alerts to (defaults to stderr).
        Pass ``None`` to disable console echo.
    file_path : str or Path, optional
        If given, alert records are also appended to this JSON Lines file.
    """

    def __init__(
        self,
        stream: TextIO | None = sys.stderr,
        file_path: str | Path | None = None,
    ) -> None:
        self.stream = stream
        self.file_path = Path(file_path) if file_path is not None else None
        self.records: list[dict] = []
        if self.file_path is not None:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self.file_path.write_text("", encoding="utf-8")

    def emit(self, violation: Violation) -> dict:
        """Emit one alert record for ``violation`` and return the record."""
        record = {
            "alert": "surface_check_failed",
            "check": violation.check,
            "expiry": violation.expiry,
            "strike": violation.strike,
            "severity": violation.severity,
            "detail": violation.detail,
            "emitted_at": datetime.now(timezone.utc).isoformat(),
        }
        self.records.append(record)
        line = json.dumps(record)
        if self.stream is not None:
            print(f"ALERT {line}", file=self.stream, flush=True)
        if self.file_path is not None:
            with self.file_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return record

    def __len__(self) -> int:
        return len(self.records)
