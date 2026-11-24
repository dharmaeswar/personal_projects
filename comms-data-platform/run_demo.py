"""Serve the gold layer the way the real platform does: API + MCP tools.

Usage: python run_demo.py [--out DIR]
Runs the pipeline if the output directory has no gold table yet, then
shows the API and MCP surfaces answering real questions against it.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from comms_platform.catalog import Catalog
from comms_platform.lake import Lake
from comms_platform.pipeline import run_pipeline
from comms_platform.serving import CommsDataAPI, MCPServer


def main():
    parser = argparse.ArgumentParser(description="Demo the API + MCP serving layer.")
    parser.add_argument("--out", default="comms_tables", help="pipeline output directory")
    args = parser.parse_args()
    root = Path(args.out)
    lake = Lake(root / "lake")
    if not lake.table_exists("gold", "daily_engagement"):
        print("No gold table yet — running the pipeline first.")
        run_pipeline(root)
    catalog = Catalog(root / "catalog.json")
    gold = lake.read_table("gold", "daily_engagement")
    quality = {}
    if (root / "observability_report.json").exists():
        quality = json.loads((root / "observability_report.json").read_text())
    api = CommsDataAPI(catalog, {"daily_engagement": gold}, quality_report=quality)
    mcp = MCPServer(api)

    print("== API: list_datasets ==")
    print(json.dumps(api.list_datasets(), indent=2))
    print("\n== API: query — top campaigns by opens ==")
    print(
        json.dumps(
            api.query_dataset(
                "SELECT campaign_id, SUM(total_opens) AS opens "
                "FROM daily_engagement GROUP BY campaign_id ORDER BY opens DESC"
            ),
            indent=2,
        )
    )
    print("\n== MCP: tools/list ==")
    print(json.dumps(mcp.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}), indent=2))
    print("\n== MCP: tools/call query_dataset ==")
    print(
        json.dumps(
            mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "query_dataset",
                        "arguments": {
                            "sql": "SELECT event_date, campaign_id, total_opens "
                            "FROM daily_engagement ORDER BY total_opens DESC LIMIT 3"
                        },
                    },
                }
            ),
            indent=2,
        )
    )
    print("\n== MCP: unknown tool (structured error, no crash) ==")
    print(
        json.dumps(
            mcp.handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "drop_table", "arguments": {}},
                }
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
