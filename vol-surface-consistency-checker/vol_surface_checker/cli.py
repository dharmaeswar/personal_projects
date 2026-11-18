"""Command-line entry point: batch-check a surface file end to end.

Usage::

    python -m vol_surface_checker data/sample_surface.csv \
        --max-age-hours 24 \
        --report violations.json \
        --alerts alerts.jsonl

Prints a summary (quotes loaded, violations by type, RMS smile error per
expiry), writes a JSON violations report, and emits one alert record per
failed check as it is found. Exit code is 1 when any violation is found,
0 when the surface is clean.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .alerts import AlertSink
from .checks import run_all_checks
from .surface import load_surface

CHECKS_RUN = (
    "calendar_arbitrage",
    "butterfly_arbitrage",
    "strike_monotonicity",
    "stale_quote",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vol_surface_checker",
        description="Run arbitrage/consistency checks over an implied-vol surface CSV.",
    )
    parser.add_argument("input", help="path to the surface CSV file")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=24.0,
        help="maximum allowed quote age in hours before a quote is stale "
        "(default: 24)",
    )
    parser.add_argument(
        "--report",
        default="violations.json",
        help="where to write the JSON violations report (default: violations.json)",
    )
    parser.add_argument(
        "--alerts",
        default=None,
        help="optional path for the JSON Lines alert stream",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    surface = load_surface(args.input)
    sink = AlertSink(stream=sys.stderr, file_path=args.alerts)
    report = run_all_checks(
        surface, max_age_hours=args.max_age_hours, on_violation=sink.emit
    )

    counts = report.counts_by_check()
    print(f"Loaded {report.quotes_checked} quotes from {args.input}")
    print(f"Checks run: {', '.join(CHECKS_RUN)} (+ RMS smile error per expiry)")
    if report.ok:
        print("Result: PASS -- no violations found.")
    else:
        print(f"Result: FAIL -- {len(report.violations)} violation(s):")
        for check in CHECKS_RUN:
            if counts.get(check):
                print(f"  {check}: {counts[check]}")
    print("RMS smile error by expiry (vol points):")
    for expiry, rms in sorted(report.rms_by_expiry.items()):
        print(f"  T={expiry:g}: {rms:.4f}")

    report_path = Path(args.report)
    report_path.write_text(
        json.dumps(
            {
                "input": str(args.input),
                "quotes_checked": report.quotes_checked,
                "ok": report.ok,
                "violations": [v.to_dict() for v in report.violations],
                "rms_smile_error_by_expiry": {
                    str(k): v for k, v in sorted(report.rms_by_expiry.items())
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Violations report written to {report_path}")
    if args.alerts:
        print(f"{len(sink)} alert record(s) written to {args.alerts}")
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
