"""End-to-end pipeline: registry -> MCP server -> agentic investigation."""

import json

from quality_platform import seed
from quality_platform.agents import run_investigation
from quality_platform.evaluate import monitor, run_evals
from quality_platform.mcp import MCPClient, MCPServer


def build_system():
    """Registry + MCP server + client, ready to use."""
    registry = seed.build_registry()
    server = MCPServer(registry)
    client = MCPClient(server)
    client.initialize()
    return registry, server, client


def run(question="Why did batch release cycle time rise from Q2 to Q3?"):
    """Run one investigation plus the eval suite; return a report dict."""
    registry, server, client = build_system()
    trajectory = run_investigation(question, client)
    evals = run_evals(client)
    health = monitor([{"pass_rate": 1.0, "mean_latency_ms": 120},
                      {"pass_rate": evals["pass_rate"], "mean_latency_ms": 125}])
    return {
        "question": question,
        "answer": trajectory["answer"],
        "investigation_passed": trajectory["passed"],
        "tool_calls": len(trajectory["tool_calls"]),
        "evals_passed": evals["passed"],
        "evals_total": evals["total"],
        "eval_pass_rate": evals["pass_rate"],
        "monitor_alert": health["alert"],
        "monitor_reasons": health["reasons"],
        "products": [registry.product_card(p) for p in registry.list_live()],
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, indent=2, default=str))
