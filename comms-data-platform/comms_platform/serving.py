"""Serving layer — REST-style API + MCP tool server.

The real platform serves lake data to web applications through backend
APIs (Java/DynamoDB) and to AI agents through MCP tool integrations. This
module models both surfaces locally in plain Python:

- `CommsDataAPI` — the read API a web app would call: list datasets,
  describe one, run a read-only query, fetch the latest quality report.
  Every response is a plain dict, the way a JSON API body would look.
- `MCPServer` — a JSON-RPC-style tool server exposing three tools to AI
  agents: `list_datasets`, `describe_dataset`, `query_dataset`. Unknown
  tools and bad arguments return structured errors, never exceptions.
"""

from __future__ import annotations

from .query import QueryEngine


class CommsDataAPI:
    """Read API over the catalog, the gold layer and the quality reports."""

    def __init__(self, catalog, gold_tables, quality_report=None):
        self.catalog = catalog
        self.engine = QueryEngine(gold_tables)
        self.quality_report = quality_report or {}

    def list_datasets(self):
        return {"datasets": self.catalog.list_names()}

    def describe_dataset(self, name):
        return {"dataset": self.catalog.describe(name)}

    def query_dataset(self, sql):
        return {"rows": self.engine.query(sql)}

    def get_quality_report(self):
        return {"quality": self.quality_report}


class MCPServer:
    """Minimal MCP-style tool server: tools, dispatch, structured errors."""

    def __init__(self, api):
        self.api = api
        self.tools = {
            "list_datasets": {
                "description": "List datasets registered in the data catalog.",
                "parameters": {},
            },
            "describe_dataset": {
                "description": "Describe one registered dataset: schema, partitions, owner.",
                "parameters": {"name": "dataset name (string, required)"},
            },
            "query_dataset": {
                "description": "Run a read-only SELECT query over the gold layer.",
                "parameters": {"sql": "SELECT statement (string, required)"},
            },
        }

    def list_tools(self):
        return {"tools": self.tools}

    def call_tool(self, name, arguments=None):
        arguments = arguments or {}
        if name not in self.tools:
            return {"error": f"unknown tool: {name}"}
        try:
            if name == "list_datasets":
                return {"result": self.api.list_datasets()}
            if name == "describe_dataset":
                if "name" not in arguments:
                    return {"error": "describe_dataset requires 'name'"}
                return {"result": self.api.describe_dataset(arguments["name"])}
            if name == "query_dataset":
                if "sql" not in arguments:
                    return {"error": "query_dataset requires 'sql'"}
                return {"result": self.api.query_dataset(arguments["sql"])}
        except (KeyError, ValueError) as exc:
            return {"error": str(exc)}
        return {"error": f"unhandled tool: {name}"}

    def handle_request(self, request):
        """Handle one JSON-RPC-style request dict.

        Expected shape: {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": ..., "arguments": {...}}}.
        """
        method = request.get("method")
        req_id = request.get("id")
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": self.list_tools()}
        if method == "tools/call":
            params = request.get("params", {})
            result = self.call_tool(params.get("name"), params.get("arguments"))
            if "error" in result:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": result["error"]},
                }
            return {"jsonrpc": "2.0", "id": req_id, "result": result["result"]}
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"unknown method: {method}"},
        }
