"""Command-line interface for pkgtool.

Usage:
    python -m pkgtool.cli analyze <package-dir> [--format text|json] [--out FILE]
    python -m pkgtool.cli cycles <package-dir>
    python -m pkgtool.cli api <package-dir>
    python -m pkgtool.cli check <package-dir>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pkgtool.api import extract_api_surface
from pkgtool.checks import run_checks
from pkgtool.cycles import find_cycles
from pkgtool.graph import build_graph
from pkgtool.report import json_report, text_report


def _analyze(args: argparse.Namespace) -> int:
    graph = build_graph(args.package)
    cycles = find_cycles(graph)
    surface = extract_api_surface(args.package)
    checks = run_checks(args.package)
    out = json_report(graph, cycles, surface, checks) if args.format == "json" else text_report(
        graph, cycles, surface, checks
    )
    if args.out:
        Path(args.out).write_text(out, encoding="utf-8")
    else:
        sys.stdout.write(out)
    errors = [c for c in checks if c.level == "error"]
    return 1 if (errors or cycles) else 0


def _cycles(args: argparse.Namespace) -> int:
    graph = build_graph(args.package)
    cycles = find_cycles(graph)
    if not cycles:
        print("no dependency cycles")
        return 0
    for c in cycles:
        print(" -> ".join(c + [c[0]]))
    return 1


def _api(args: argparse.Namespace) -> int:
    surface = extract_api_surface(args.package)
    for mod in sorted(surface):
        names = surface[mod].public_names
        print(f"{mod}: {', '.join(names) if names else '(none)'}")
    return 0


def _check(args: argparse.Namespace) -> int:
    checks = run_checks(args.package)
    for c in checks:
        where = f" [{c.path}]" if c.path else ""
        print(f"[{c.level.upper()}] {c.code}: {c.message}{where}")
    return 1 if any(c.level == "error" for c in checks) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pkgtool", description="Analyze a Python package.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("analyze", help="full analysis: graph, cycles, API surface, checks")
    p.add_argument("package", help="path to the package directory")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--out", help="write the report to FILE instead of stdout")
    p.set_defaults(func=_analyze)

    p = sub.add_parser("cycles", help="list dependency cycles only")
    p.add_argument("package")
    p.set_defaults(func=_cycles)

    p = sub.add_parser("api", help="list the public API surface only")
    p.add_argument("package")
    p.set_defaults(func=_api)

    p = sub.add_parser("check", help="run build-metadata / lint checks only")
    p.add_argument("package")
    p.set_defaults(func=_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
