"""Run the streaming ingest demo and the observability monitors.

Simulates a day of order events arriving in micro-batches, processes
them exactly once into the accepted set, then runs freshness, volume,
and schema-drift monitors on the result. Writes ``streaming_report.txt``
and ``observability_report.txt`` next to this script.

Timestamps are synthetic (seeded, Nov 17 2026), so "now" for the
freshness check is simulated as five minutes after the last ingested
event — the same way a replay of a recorded stream would be evaluated.
The volume baseline is four prior simulated daily totals.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from lakehouse.observability import render_observability_report, run_observability
from lakehouse.streaming import generate_event_stream, run_stream

HERE = Path(__file__).resolve().parent
PRIOR_DAILY_TOTALS = [118, 121, 119, 120]


def main() -> None:
    stream = generate_event_stream()
    result = run_stream(stream)
    accepted = result["accepted"]
    lines = ["STREAMING INGEST REPORT", ""]
    lines.append(f"arrived: {result['total_arrived']} events")
    lines.append(f"accepted: {len(accepted)} events")
    lines.append(f"late dropped: {len(result['late'])} events")
    lines.append(f"duplicates dropped: {len(result['duplicates'])} events")
    lines.append("")
    for batch in result["batches"]:
        lines.append(
            f"batch {batch['batch']}: arrived {batch['arrived']}, "
            f"accepted {batch['accepted']}, late {batch['late_dropped']}, "
            f"duplicates {batch['duplicates_dropped']}, watermark {batch['watermark']}"
        )
    lines.append("")
    lines.append(f"checkpoint offset: {result['checkpoint'].last_offset}")
    (HERE / "streaming_report.txt").write_text("\n".join(lines) + "\n")
    now = pd.to_datetime(accepted["ingested_at"]).max() + pd.Timedelta(minutes=5)
    monitors = run_observability(
        accepted,
        "event_time",
        now,
        list(accepted.columns),
        PRIOR_DAILY_TOTALS,
    )
    (HERE / "observability_report.txt").write_text(render_observability_report(monitors))
    print("\n".join(lines))
    print(render_observability_report(monitors))


if __name__ == "__main__":
    main()
