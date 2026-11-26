"""MCP server connecting AI agents to enterprise Quality data.

A small JSON-RPC 2.0 server in the shape of the Model Context Protocol:
`initialize`, `tools/list`, `tools/call` and `ping`. Each tool declares a
JSON input schema; arguments are validated before dispatch and every
failure is a structured error, never an exception leak. The tools read
only the FAIR registry and the seeded synthetic data — no live enterprise
system is touched.
"""

import json

from quality_platform import seed
from quality_platform.fair import RegistryError

TOOL_SCHEMAS = {
    "search_data_products": {
        "description": "Search FAIR data products by keyword.",
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string"},
                "domain": {"type": "string"},
                "min_quality": {"type": "integer"},
            },
        },
    },
    "get_product_metadata": {
        "description": "Full metadata for one FAIR data product.",
        "inputSchema": {
            "type": "object",
            "required": ["product_id"],
            "properties": {"product_id": {"type": "string"}},
        },
    },
    "run_quality_check": {
        "description": "Run completeness, range and duplicate checks on a product dataset.",
        "inputSchema": {
            "type": "object",
            "required": ["product_id"],
            "properties": {"product_id": {"type": "string"}},
        },
    },
    "get_quality_metrics": {
        "description": "Aggregate batch release metrics, optionally for one quarter.",
        "inputSchema": {
            "type": "object",
            "required": [],
            "properties": {"quarter": {"type": "string"}},
        },
    },
    "list_lineage": {
        "description": "Lineage entries tracing a product to source and transform.",
        "inputSchema": {
            "type": "object",
            "required": ["product_id"],
            "properties": {"product_id": {"type": "string"}},
        },
    },
}

# Which seeded rows back each product's quality check.
_PRODUCT_ROWS = {
    "batch-release": seed.BATCHES,
    "deviation-register": seed.DEVIATIONS,
    "capa-tracker": seed.CAPAS,
}


def _error(code, message):
    return {"code": code, "message": message}


def _check_rows(rows):
    """Completeness, range and duplicate checks over a list of dicts."""
    findings = []
    if not rows:
        return {"passed": False, "checks": ["no rows to check"], "findings": findings}
    keys = set(rows[0].keys())
    missing = [i for i, r in enumerate(rows) if set(r.keys()) != keys]
    if missing:
        findings.append(f"{len(missing)} rows with inconsistent fields")
    empty = [i for i, r in enumerate(rows)
             if any(v is None or v == "" for v in r.values())]
    if empty:
        findings.append(f"{len(empty)} rows with empty values")
    seen, dupes = set(), 0
    for r in rows:
        key = json.dumps(r, sort_keys=True, default=str)
        if key in seen:
            dupes += 1
        seen.add(key)
    if dupes:
        findings.append(f"{dupes} duplicate rows")
    for row in rows:
        for name, value in row.items():
            if isinstance(value, (int, float)) and value < 0:
                findings.append(f"negative value in {name}: {value}")
                break
    return {"passed": not findings, "checks": ["completeness", "range", "duplicates"],
            "rows_checked": len(rows), "findings": findings}


class MCPServer:
    """In-process MCP server backed by a FAIR registry."""

    def __init__(self, registry):
        self.registry = registry

    def handle(self, request):
        """Handle one JSON-RPC 2.0 request dict; always returns a response."""
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
            return {"jsonrpc": "2.0", "id": None,
                    "error": _error(-32600, "invalid request: expected JSON-RPC 2.0")}
        method = request.get("method")
        req_id = request.get("id")
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": req_id,
                    "result": {"protocolVersion": "2024-11-05",
                               "serverInfo": {"name": "quality-mcp-server",
                                              "version": "1.0.0"}}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        if method == "tools/list":
            tools = [{"name": name, **schema}
                     for name, schema in TOOL_SCHEMAS.items()]
            return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
        if method == "tools/call":
            return self._call_tool(request.get("params") or {}, req_id)
        return {"jsonrpc": "2.0", "id": req_id,
                "error": _error(-32601, f"method not found: {method}")}

    def _call_tool(self, params, req_id):
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOL_SCHEMAS:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": _error(-32602, f"unknown tool: {name}")}
        schema = TOOL_SCHEMAS[name]["inputSchema"]
        for field in schema.get("required", []):
            if field not in args:
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": _error(-32602, f"missing required argument: {field}")}
        for field, value in args.items():
            expected = schema["properties"].get(field, {}).get("type")
            if expected == "string" and not isinstance(value, str):
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": _error(-32602, f"argument {field} must be a string")}
            if expected == "integer" and not isinstance(value, int):
                return {"jsonrpc": "2.0", "id": req_id,
                        "error": _error(-32602, f"argument {field} must be an integer")}
        try:
            result = self._dispatch(name, args)
        except RegistryError as exc:
            return {"jsonrpc": "2.0", "id": req_id,
                    "error": _error(-32000, str(exc))}
        return {"jsonrpc": "2.0", "id": req_id,
                "result": {"content": [{"type": "text",
                                        "text": json.dumps(result, default=str)}]}}

    def _dispatch(self, name, args):
        if name == "search_data_products":
            products = self.registry.search(
                args["query"], domain=args.get("domain"),
                min_quality=args.get("min_quality"))
            return {"products": [self.registry.product_card(p) for p in products]}
        if name == "get_product_metadata":
            product = self.registry.get(args["product_id"])
            if product is None:
                raise RegistryError(f"unknown product_id: {args['product_id']}")
            return {"product": product}
        if name == "run_quality_check":
            product = self.registry.get(args["product_id"])
            if product is None:
                raise RegistryError(f"unknown product_id: {args['product_id']}")
            return _check_rows(_PRODUCT_ROWS[args["product_id"]])
        if name == "get_quality_metrics":
            metrics = seed.batch_metrics(args.get("quarter"))
            if metrics is None:
                raise RegistryError(f"no batch data for quarter: {args.get('quarter')}")
            breakdown = seed.deviation_breakdown(args.get("quarter"))
            return {"metrics": metrics, "deviations": breakdown}
        if name == "list_lineage":
            return {"lineage": self.registry.lineage(args["product_id"])}
        raise RegistryError(f"unimplemented tool: {name}")


class MCPClient:
    """Thin client that talks to an MCPServer over dict requests."""

    def __init__(self, server):
        self.server = server
        self._next_id = 0

    def _request(self, method, params=None):
        self._next_id += 1
        response = self.server.handle(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method,
             "params": params or {}})
        if "error" in response:
            raise RuntimeError(response["error"]["message"])
        return response["result"]

    def initialize(self):
        return self._request("initialize")

    def list_tools(self):
        return self._request("tools/list")["tools"]

    def call_tool(self, name, arguments):
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        return json.loads(result["content"][0]["text"])
