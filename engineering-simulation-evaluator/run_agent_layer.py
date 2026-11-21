"""Demo: an AI coding agent drives the simulators end to end through the MCP layer.

Usage: python run_agent_layer.py

The agent (a) lists the tools, (b) runs a simulation, (c) compares the
result with the golden reference, (d) proposes a no-op model change and
lands it with evidence, and (e) proposes a change that moves the outputs
and watches the CI guardrails block it. All data is synthetic and local.
"""

from eng_sim_evaluator.mcp_server import dispatch


def call(request_id: int, tool: str, arguments: dict, agent_id: str = "demo-agent") -> dict:
    response = dispatch(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments, "agent_id": agent_id},
        }
    )
    return response


def main() -> None:
    print("=== 1. Agent lists the tools ===")
    tools = dispatch({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    for tool in tools["result"]["tools"]:
        print(f"- {tool['name']}: {tool['description']}")

    print("\n=== 2. Agent runs a simulation ===")
    run = call(2, "run_simulation", {"case": "steel-100mm"})
    print(run["result"]["outputs"])
    print("provenance:", run["result"]["provenance"]["inputs_hash"][:12], "...")

    print("\n=== 3. Agent compares the result with the golden reference ===")
    compared = call(
        3,
        "compare_golden",
        {"case": "steel-100mm", "outputs": run["result"]["outputs"]},
    )
    print("golden comparison passed:", compared["result"]["passed"])

    print("\n=== 4. Agent proposes a no-op change and lands it with evidence ===")
    landed = call(4, "land_change", {"case": "steel-100mm", "change": {}})
    print("gate:", landed["result"]["gate"])

    print("\n=== 5. Agent proposes a change that moves the outputs ===")
    blocked = call(
        5,
        "land_change",
        {"case": "steel-100mm", "change": {"height_m": 0.12}},
    )
    print("gate:", blocked["result"]["gate"])

    print("\n=== 6. Agent proposes a malformed change ===")
    malformed = call(
        6,
        "land_change",
        {"case": "steel-100mm", "change": {"height_m": -0.05, "surprise": True}},
    )
    print("gate:", malformed["result"]["gate"])


if __name__ == "__main__":
    main()
