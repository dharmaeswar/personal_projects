"""Command-line interface for Safety Intelligence Analytics."""

from __future__ import annotations

import argparse
import sys

from .anomaly import find_anomalies
from .data import generate_events, monthly_counts
from .report import build_briefing, render_briefing_json, render_briefing_text
from .risk import risk_scores
from .trends import emerging_risks, monthly_rates


def _load():
    events, exposure = generate_events()
    counts = monthly_counts(events, exposure)
    return counts, exposure


def cmd_trends(_args: argparse.Namespace) -> int:
    counts, exposure = _load()
    rates = monthly_rates(counts, exposure)
    for hit in emerging_risks(rates):
        print(
            f"{hit['category']}: latest {hit['recent_rate']} vs baseline "
            f"{hit['baseline_rate']} per 10k flights, "
            f"z={hit['max_recent_z']}, slope {hit['slope_per_month']}/month"
        )
    return 0


def cmd_anomalies(_args: argparse.Namespace) -> int:
    counts, exposure = _load()
    rates = monthly_rates(counts, exposure)
    for hit in find_anomalies(rates):
        print(
            f"{hit['month']} {hit['category']}: rate {hit['rate']} "
            f"above fence {hit['upper_fence']} (z={hit['z']})"
        )
    return 0


def cmd_risks(_args: argparse.Namespace) -> int:
    counts, exposure = _load()
    rates = monthly_rates(counts, exposure)
    for rank, row in enumerate(risk_scores(rates), start=1):
        print(
            f"{rank}. {row['category']}: score {row['score']} "
            f"(rate {row['recent_rate']}, trend {row['trend']})"
        )
    return 0


def cmd_briefing(args: argparse.Namespace) -> int:
    counts, exposure = _load()
    briefing = build_briefing(counts, exposure)
    if args.json:
        print(render_briefing_json(briefing))
    else:
        print(render_briefing_text(briefing))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="safetyint",
        description="Safety Intelligence analytics over synthetic safety data.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("trends", help="List emerging risks vs baseline.")
    sub.add_parser("anomalies", help="List anomalous months per category.")
    sub.add_parser("risks", help="Rank categories by risk score.")
    briefing = sub.add_parser("briefing", help="Print the full briefing.")
    briefing.add_argument("--json", action="store_true", help="JSON output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handlers = {
        "trends": cmd_trends,
        "anomalies": cmd_anomalies,
        "risks": cmd_risks,
        "briefing": cmd_briefing,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
