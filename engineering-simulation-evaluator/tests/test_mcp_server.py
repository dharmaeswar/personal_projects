"""Tests for mcp_server.py: MCP-style JSON-RPC tool layer."""

import json
import subprocess
import sys

import pytest

from eng_sim_evaluator.golden import compute_outputs
from eng_sim_evaluator.mcp_server import dispatch

AGENT = "test-agent"


def _call(request_id, tool, arguments, agent_id=AGENT):
    return dispatch(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments, "agent_id": agent_id},
        }
    )


def test_tools_list_advertises_three_tools():
    response = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [t["name"] for t in response["result"]["tools"]]
    assert names == ["run_simulation", "compare_golden", "land_change"]


def test_run_simulation_returns_structured_outputs_and_provenance():
    response = _call(2, "run_simulation", {"case": "steel-100mm"})
    result = response["result"]
    assert result["case"] == "steel-100mm"
    assert result["outputs"]["tip_deflection_m"] == pytest.approx(0.0016)
    assert result["provenance"]["tool"] == "run_simulation"
    assert result["provenance"]["agent_id"] == AGENT
    assert result["provenance"]["golden_version"] == "golden-v1"


def test_run_simulation_rejects_unknown_case():
    response = _call(3, "run_simulation", {"case": "nope"})
    assert "error" in response
    assert response["error"]["code"] == -32602


def test_compare_golden_passes_for_golden_outputs():
    from eng_sim_evaluator.beam import Beam

    beam = Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9)
    response = _call(
        4, "compare_golden", {"case": "steel-100mm", "outputs": compute_outputs(beam, 1000.0)}
    )
    assert response["result"]["passed"]


def test_compare_golden_reports_moved_field():
    from eng_sim_evaluator.beam import Beam

    beam = Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9)
    outputs = compute_outputs(beam, 1000.0)
    outputs["max_stress_pa"] += 500.0
    response = _call(5, "compare_golden", {"case": "steel-100mm", "outputs": outputs})
    assert not response["result"]["passed"]


def test_land_change_allows_no_op_and_blocks_moved_outputs():
    allowed = _call(6, "land_change", {"case": "steel-100mm", "change": {}})
    assert allowed["result"]["gate"]["allowed"]
    blocked = _call(7, "land_change", {"case": "steel-100mm", "change": {"height_m": 0.12}})
    assert not blocked["result"]["gate"]["allowed"]


def test_unknown_tool_and_method_return_errors():
    assert "error" in _call(8, "fly_rocket", {})
    assert "error" in dispatch({"jsonrpc": "2.0", "id": 9, "method": "explode"})


def test_stdio_server_round_trips_one_request():
    request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    proc = subprocess.run(
        [sys.executable, "-m", "eng_sim_evaluator.mcp_server"],
        input=request + "\n",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 0
    response = json.loads(proc.stdout.strip().splitlines()[-1])
    assert response["result"]["tools"][0]["name"] == "run_simulation"
