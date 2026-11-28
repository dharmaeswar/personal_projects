"""MCP tool server over the analytics warehouse (stdio, JSON-RPC 2.0).

Lets an AI-native client (Claude Code, Codex, or any MCP client) query the
modelled warehouse through named tools instead of raw SQL, so stakeholders
can self-serve the same trusted metrics the reporting queries produce:

- warehouse_health               data-quality checks + freshness SLA
- service_adoption_trend         monthly adoption / cost by service
- revenue_driver_by_service_region  cost share by service and region
- cost_per_account               cost and usage per account
- daily_cost_trend               daily cost / usage trend

Implementation notes (honest limits):

- This is a hand-rolled JSON-RPC 2.0 server using only the Python standard
  library — it implements the MCP surface (initialize, tools/list,
  tools/call, ping) directly and does NOT depend on the MCP Python SDK.
- The server opens the warehouse read-only (SQLite URI mode=ro) and only
  ever runs the fixed reporting queries from src/analytics.py, so a tool
  call can never write to the warehouse or run arbitrary SQL.
- Tool results are returned as JSON text content, one tool result per call.

Usage (from the project root, after a warehouse exists)::

    python -m src.run --run-date 2026-11-13
    python -m src.mcp_server --db output/warehouse.db

Then send one JSON-RPC request object per line on stdin, e.g.::

    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "demo", "version": "0.1"}}}
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
     "params": {"name": "revenue_driver_by_service_region", "arguments": {"limit": 5}}}
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.analytics import QUERIES  # noqa: E402
from src.quality import run_all_checks  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "analytics-warehouse"
SERVER_VERSION = "0.2.0"

MAX_LIMIT = 500
DEFAULT_LIMIT = 100

TOOL_DESCRIPTIONS = {
    "warehouse_health": (
        "Run every data-quality check (referential integrity, null/negative "
        "usage, duplicate events, SCD2 overlaps) plus the freshness SLA "
        "check and return pass/fail per check."
    ),
    "service_adoption_trend": (
        "Monthly service adoption: active days, total usage, total cost and "
        "distinct accounts per service, from the modelled star schema."
    ),
    "revenue_driver_by_service_region": (
        "Cost and usage by service and region, with each row's share of "
        "total cost, from the modelled star schema."
    ),
    "cost_per_account": (
        "Usage days, total / average / max daily cost per account, from the "
        "modelled star schema."
    ),
    "daily_cost_trend": (
        "Daily total cost and usage trend, from the modelled star schema."
    ),
}

TOOL_INPUT_SCHEMAS = {
    "warehouse_health": {
        "type": "object",
        "properties": {
            "run_date": {
                "type": "string",
                "description": "Run date YYYY-MM-DD used for the freshness SLA check (default: today).",
            }
        },
    },
    "service_adoption_trend": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    "revenue_driver_by_service_region": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    "cost_per_account": {"type": "object", "properties": {"limit": {"type": "integer"}}},
    "daily_cost_trend": {"type": "object", "properties": {"limit": {"type": "integer"}}},
}


def _open_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"warehouse not found: {db_path} (run python -m src.run first)")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _limit(arguments: dict) -> int:
    raw = arguments.get("limit", DEFAULT_LIMIT)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError("limit must be an integer")
    if raw < 1:
        raise ValueError("limit must be at least 1")
    return min(raw, MAX_LIMIT)


def _tool_result(payload) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def _call_tool(db_path: str, name: str, arguments: dict) -> dict:
    if name == "warehouse_health":
        run_date = arguments.get("run_date")
        if run_date is not None and not isinstance(run_date, str):
            raise ValueError("run_date must be a string YYYY-MM-DD")
        conn = _open_read_only(db_path)
        try:
            checks = run_all_checks(conn, run_date=run_date)
        finally:
            conn.close()
        return _tool_result(
            {"all_checks_passed": all(c["passed"] for c in checks), "checks": checks}
        )
    if name in QUERIES:
        limit = _limit(arguments)
        conn = _open_read_only(db_path)
        try:
            rows = conn.execute(QUERIES[name]).fetchall()
        finally:
            conn.close()
        return _tool_result({"tool": name, "rows_returned": min(len(rows), limit),
                             "rows": [dict(r) for r in rows[:limit]]})
    raise ValueError(f"unknown tool: {name}")


def _error_response(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(request: dict, db_path: str) -> dict | None:
    """Handle one decoded JSON-RPC request object. Returns None for notifications."""
    req_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}
    if not isinstance(params, dict):
        return _error_response(req_id, -32602, "params must be an object")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": TOOL_DESCRIPTIONS[name],
                        "inputSchema": TOOL_INPUT_SCHEMAS[name],
                    }
                    for name in TOOL_DESCRIPTIONS
                ]
            },
        }
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or not name:
            return _error_response(req_id, -32602, "tools/call requires a tool name")
        if not isinstance(arguments, dict):
            return _error_response(req_id, -32602, "arguments must be an object")
        try:
            result = _call_tool(db_path, name, arguments)
        except FileNotFoundError as exc:
            return _error_response(req_id, -32602, str(exc))
        except ValueError as exc:
            return _error_response(req_id, -32602, str(exc))
        except sqlite3.Error as exc:
            return _error_response(req_id, -32603, f"warehouse query failed: {exc}")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    return _error_response(req_id, -32601, f"method not found: {method}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP tool server over the analytics warehouse")
    parser.add_argument("--db", default="output/warehouse.db")
    args = parser.parse_args()
    db_path = str(Path(args.db).resolve()) if not Path(args.db).is_absolute() else args.db
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps(_error_response(None, -32700, f"parse error: {exc}")), flush=True)
            continue
        if not isinstance(request, dict) or "method" not in request:
            print(json.dumps(_error_response(request.get("id") if isinstance(request, dict) else None,
                                            -32600, "invalid request: expected a JSON-RPC object with a method")),
                  flush=True)
            continue
        response = handle_request(request, db_path)
        if response is not None:
            print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
