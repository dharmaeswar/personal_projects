"""Command-line tool for the integration surface.

Usage:
    python -m integration_surface.cli list-tools
    python -m integration_surface.cli analyze orders
    python -m integration_surface.cli transform orders customers
    python -m integration_surface.cli transform-batch orders customers orders
    python -m integration_surface.cli dry-run orders
    python -m integration_surface.cli validate 1000 1000
    python -m integration_surface.cli suggest "map the orders table" --seed 7
    python -m integration_surface.cli diagnostics amp.analyze_schema
"""

from __future__ import annotations

import argparse
import json
import sys

from .context import CallerContext
from .sdk import IntegrationClient


def _client() -> IntegrationClient:
    ctx = CallerContext(
        user_id="demo-user", tenant_id="tenant-demo",
        scopes=frozenset({"amp:read", "amp:migrate"}),
        auth_mechanism="api_key",
    )
    return IntegrationClient(ctx)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="amp-integrations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-tools", help="list discoverable tools")
    p = sub.add_parser("analyze", help="analyze a legacy schema")
    p.add_argument("schema")
    p = sub.add_parser("transform", help="transform one table")
    p.add_argument("schema"); p.add_argument("table")
    p.add_argument("--strategy", default="auto", choices=["auto", "embed", "reference"])
    p = sub.add_parser("transform-batch", help="transform several tables")
    p.add_argument("schema"); p.add_argument("tables", nargs="+")
    p = sub.add_parser("dry-run", help="simulate a migration")
    p.add_argument("schema")
    p = sub.add_parser("validate", help="validate migrated rows")
    p.add_argument("source_rows", type=int); p.add_argument("migrated_rows", type=int)
    p = sub.add_parser("suggest", help="ask the model for a mapping suggestion")
    p.add_argument("prompt"); p.add_argument("--seed", type=int, default=0)
    p = sub.add_parser("diagnostics", help="show metrics and recent failures for a tool")
    p.add_argument("tool")

    args = parser.parse_args(argv)
    client = _client()
    if args.command == "list-tools":
        print(json.dumps(client.list_tools(), indent=2))
        return 0
    if args.command == "analyze":
        result = client.analyze_schema(args.schema)
    elif args.command == "transform":
        result = client.transform_table(args.schema, args.table, args.strategy)
    elif args.command == "transform-batch":
        result = client.transform_batch(args.schema, args.tables)
    elif args.command == "dry-run":
        result = client.dry_run_migration(args.schema)
    elif args.command == "validate":
        result = client.validate_migrated(args.source_rows, args.migrated_rows)
    elif args.command == "suggest":
        result = client.suggest_mapping(args.prompt, seed=args.seed)
    elif args.command == "diagnostics":
        print(json.dumps(client.registry.observer.diagnostics(args.tool), indent=2))
        return 0
    else:  # pragma: no cover
        parser.error(f"unknown command {args.command}")
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
