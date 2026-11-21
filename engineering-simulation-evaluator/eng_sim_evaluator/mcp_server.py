"""MCP-style tool server: the layer AI coding agents call to drive simulators.

Implements the Model Context Protocol shape over JSON-RPC 2.0 (stdlib only,
no MCP SDK): `tools/list` advertises the tools, `tools/call` runs one.
Every tool returns structured output, a reproducible result, and a
provenance record, and reports errors in a form an agent can act on.

Tools:
- run_simulation — run the analytic beam simulator for a case and return
  structured outputs (tip deflection, stress, natural frequency).
- compare_golden — compare a candidate output set with the frozen golden
  reference for a case and report per-field diffs.
- land_change — run the CI guardrails on an agent-proposed model change
  and report whether it may land, with every failed guardrail listed.

Run as a stdio server (`python -m eng_sim_evaluator.mcp_server`) or call
`dispatch(request)` in-process. All data is synthetic and local; no real
simulator, cluster, or production system is involved.
"""

from __future__ import annotations

import json
import sys

from .beam import Beam
from .golden import (
    GOLDEN_VERSION,
    compare_golden,
    compute_outputs,
    generate_golden,
)
from .guardrails import gate_change
from .provenance import Provenance, record_provenance

# The shared simulation cases every tool works from.
_CASES = [
    ("steel-100mm", Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9), 1000.0),
    ("steel-50mm", Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9), 1000.0),
    ("aluminium-80mm", Beam(length=2.0, width=0.1, height=0.08, youngs_modulus=70e9, density=2700.0), 1000.0),
]

_GOLDEN = generate_golden(_CASES)

TOOL_SCHEMAS = {
    "run_simulation": {
        "description": "Run the analytic beam simulator for a golden case and return structured outputs.",
        "input_schema": {
            "type": "object",
            "properties": {"case": {"type": "string"}},
            "required": ["case"],
        },
    },
    "compare_golden": {
        "description": "Compare candidate simulator outputs against the frozen golden reference for a case.",
        "input_schema": {
            "type": "object",
            "properties": {
                "case": {"type": "string"},
                "outputs": {"type": "object"},
            },
            "required": ["case", "outputs"],
        },
    },
    "land_change": {
        "description": "Run the CI guardrails on an agent-proposed model change to one case; it lands only if every guardrail passes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string"},
                "case": {"type": "string"},
                "change": {"type": "object"},
            },
            "required": ["agent_id", "case", "change"],
        },
    },
}


def _error(code: int, message: str) -> dict:
    return {"code": code, "message": message}


def _result(payload: dict, provenance: Provenance) -> dict:
    payload = dict(payload)
    payload["provenance"] = provenance.as_dict()
    return payload


def _call_run_simulation(args: dict, agent_id: str) -> dict:
    case_name = args.get("case")
    if not isinstance(case_name, str) or case_name not in _GOLDEN:
        return {"error": _error(-32602, f"unknown case: {case_name!r}")}
    case = _GOLDEN[case_name]
    outputs = compute_outputs(case.beam, case.load)
    result = {"case": case_name, "outputs": outputs, "golden_version": GOLDEN_VERSION}
    return {"result": _result(result, record_provenance("run_simulation", agent_id, args, result, GOLDEN_VERSION))}


def _call_compare_golden(args: dict, agent_id: str) -> dict:
    case_name = args.get("case")
    outputs = args.get("outputs")
    if not isinstance(case_name, str) or case_name not in _GOLDEN:
        return {"error": _error(-32602, f"unknown case: {case_name!r}")}
    if not isinstance(outputs, dict):
        return {"error": _error(-32602, "outputs must be an object of field -> number")}
    try:
        comparison = compare_golden(_GOLDEN[case_name], outputs)
    except ValueError as exc:
        return {"error": _error(-32602, str(exc))}
    result = comparison.as_dict()
    return {"result": _result(result, record_provenance("compare_golden", agent_id, args, result, GOLDEN_VERSION))}


def _call_land_change(args: dict, agent_id: str) -> dict:
    case_name = args.get("case")
    change = args.get("change")
    if not isinstance(case_name, str) or case_name not in _GOLDEN:
        return {"error": _error(-32602, f"unknown case: {case_name!r}")}
    if not isinstance(change, dict):
        return {"error": _error(-32602, "change must be an object of field -> value")}
    # Provenance is built from the change itself (the evidence the gate
    # checks), then the gate runs with that record attached — so a reviewer
    # can reproduce the gate decision from the change and its record.
    evidence = {"case": case_name, "change": change}
    provenance = record_provenance("land_change", agent_id, args, evidence, GOLDEN_VERSION)
    gate = gate_change(change, _GOLDEN[case_name], provenance)
    result = {"case": case_name, "change": change, "gate": gate.as_dict()}
    return {"result": _result(result, provenance)}


def dispatch(request: dict) -> dict:
    """Handle one JSON-RPC 2.0 request and return the response dict."""
    if not isinstance(request, dict):
        return {"jsonrpc": "2.0", "id": None, "error": _error(-32600, "request must be an object")}
    request_id = request.get("id")
    method = request.get("method")
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {"name": name, **schema} for name, schema in TOOL_SCHEMAS.items()
                ]
            },
        }
    if method == "tools/call":
        params = request.get("params") or {}
        tool = params.get("name")
        args = params.get("arguments") or {}
        agent_id = params.get("agent_id") or "anonymous-agent"
        if tool not in TOOL_SCHEMAS:
            return {"jsonrpc": "2.0", "id": request_id, "error": _error(-32601, f"unknown tool: {tool!r}")}
        if not isinstance(args, dict):
            return {"jsonrpc": "2.0", "id": request_id, "error": _error(-32602, "arguments must be an object")}
        handler = {
            "run_simulation": _call_run_simulation,
            "compare_golden": _call_compare_golden,
            "land_change": _call_land_change,
        }[tool]
        outcome = handler(args, agent_id)
        return {"jsonrpc": "2.0", "id": request_id, **outcome}
    return {"jsonrpc": "2.0", "id": request_id, "error": _error(-32601, f"unknown method: {method!r}")}


def serve() -> None:
    """Read JSON-RPC requests (one per line) from stdin, write responses."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": _error(-32700, f"parse error: {exc}")}), flush=True)
            continue
        print(json.dumps(dispatch(request)), flush=True)


if __name__ == "__main__":
    serve()
