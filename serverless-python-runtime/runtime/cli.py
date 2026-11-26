"""CLI for the serverless Python runtime.

Usage:
    python -m runtime.cli package handler.py requirements.txt --out bundle/
    python -m runtime.cli invoke handler.py my_function --event '{"n": 3}'
    python -m runtime.cli bench handler.py my_function --count 5
"""

import argparse
import json
import sys

from .config import RuntimeConfig
from .executor import Executor
from .observability import log_event
from .packaging import build_bundle


def cmd_package(args: argparse.Namespace) -> int:
    config = RuntimeConfig(bundle_budget_mb=args.budget)
    config.validate()
    manifest_text = open(args.requirements, encoding="utf-8").read()
    manifest = build_bundle(
        args.handler, manifest_text, args.out, size_budget_mb=args.budget
    )
    log_event(
        "info",
        "bundle built",
        handler=manifest["handler"],
        total_bytes=manifest["total_bytes"],
        dependencies=len(manifest["dependencies"]),
    )
    print(json.dumps(manifest, indent=2))
    return 0


def cmd_invoke(args: argparse.Namespace) -> int:
    event = json.loads(args.event) if args.event else {}
    with Executor(RuntimeConfig(timeout_s=args.timeout)) as executor:
        response = executor.invoke(args.handler, args.function, event)
    print(json.dumps(response, indent=2))
    return 0 if response.get("ok") else 1


def cmd_bench(args: argparse.Namespace) -> int:
    event = json.loads(args.event) if args.event else {}
    with Executor(RuntimeConfig(timeout_s=args.timeout)) as executor:
        for _ in range(args.count):
            executor.invoke(args.handler, args.function, event)
        print(json.dumps(executor.metrics.summary(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runtime.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("package", help="build a deployment bundle")
    p.add_argument("handler")
    p.add_argument("requirements")
    p.add_argument("--out", required=True)
    p.add_argument("--budget", type=int, default=250)
    p.set_defaults(func=cmd_package)

    p = sub.add_parser("invoke", help="invoke a handler once")
    p.add_argument("handler")
    p.add_argument("function")
    p.add_argument("--event", default="{}")
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_invoke)

    p = sub.add_parser("bench", help="invoke repeatedly and print metrics")
    p.add_argument("handler")
    p.add_argument("function")
    p.add_argument("--event", default="{}")
    p.add_argument("--count", type=int, default=5)
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_bench)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
