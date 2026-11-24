"""Command line: analyze a unified diff and print a change review.

Usage:
    python -m changereview.cli analyze <diff-file>
        [--coverage coverage.json] [--owners owners.json] [--format md|json]

coverage.json maps a file path to a list of covered line numbers, e.g.
{"src/app.py": [1, 2, 3]}. owners.json maps a path prefix to reviewers,
e.g. {"src/payments/": ["payments-team"]}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .diffparse import parse_diff
from .report import to_json, to_markdown
from .review import review_change
from .signals import analyze_change


def _load_json(path: str | None) -> dict | None:
    if path is None:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def analyze(
    diff_text: str,
    coverage: dict[str, set[int]] | None = None,
    owners: dict[str, list[str]] | None = None,
):
    files = parse_diff(diff_text)
    signals = analyze_change(files, coverage=coverage)
    return review_change(signals, [f.path for f in files], owners)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="changereview")
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_cmd = sub.add_parser("analyze", help="review a unified diff file")
    analyze_cmd.add_argument("diff_file")
    analyze_cmd.add_argument("--coverage", default=None)
    analyze_cmd.add_argument("--owners", default=None)
    analyze_cmd.add_argument("--format", choices=["md", "json"], default="md")
    args = parser.parse_args(argv)

    diff_text = Path(args.diff_file).read_text(encoding="utf-8")
    coverage_raw = _load_json(args.coverage)
    coverage = (
        {path: set(lines) for path, lines in coverage_raw.items()}
        if coverage_raw is not None
        else None
    )
    owners = _load_json(args.owners)
    review = analyze(diff_text, coverage=coverage, owners=owners)
    print(to_json(review) if args.format == "json" else to_markdown(review))
    return 0 if review.verdict != "BLOCK" else 2


if __name__ == "__main__":
    sys.exit(main())
