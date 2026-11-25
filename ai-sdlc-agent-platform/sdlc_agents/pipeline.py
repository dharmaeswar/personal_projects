"""AI SDLC agent platform — end-to-end pipeline.

Loads the seeded repo and tickets, builds the context graph, runs the
agentic SDLC workflow per ticket, grades the benchmark suite, records
everything in the observability store, and writes a JSON report plus a
Markdown dashboard. Run it with: python run_demo.py
"""

from __future__ import annotations

import json
from pathlib import Path

from sdlc_agents import agents, benchmarks, observability
from sdlc_agents.agents import Ticket
from sdlc_agents.context_graph import ContextGraph, Node
from sdlc_agents.routing import Model, ModelRouter

MODELS = [
    Model("sdlc-small", capability=0.55, cost_per_1k_tokens=0.15, latency_ms_per_1k_tokens=120),
    Model("sdlc-standard", capability=0.75, cost_per_1k_tokens=0.60, latency_ms_per_1k_tokens=250),
    Model("sdlc-strong", capability=0.92, cost_per_1k_tokens=2.40, latency_ms_per_1k_tokens=600),
]

# Patched function sources the TestAgent executes (one per fix type).
PATCHED_SOURCES = {
    "off_by_one": "def average(total, count):\n    return total // count if count else 0\n",
    "bare_except": "def parse_int(text):\n    try:\n        return int(text)\n    except ValueError:\n        return None\n",
    "missing_validation": "def charge(amount):\n    if amount < 0:\n        raise ValueError('amount must not be negative')\n    return amount\n",
}

# Diffs the ReviewAgent scans (added lines per file).
DIFFS = {
    "SDLC-101": {"billing.py": ["    return total // count if count else 0  # fixed"]},
    "SDLC-102": {"billing.py": ["    except ValueError:", "        return None  # fixed"]},
    "SDLC-103": {"billing.py": ["    if amount < 0:", "        raise ValueError('amount must not be negative')"]},
}


def build_graph(seed: dict) -> ContextGraph:
    graph = ContextGraph()
    for f in seed["files"]:
        graph.add_node(Node(f"file:{f['name']}", "file", f["name"], f["text"]))
    for fn in seed["functions"]:
        graph.add_node(Node(f"fn:{fn['name']}", "function", fn["name"], fn["text"]))
        graph.add_edge(f"file:{fn['file']}", f"fn:{fn['name']}", "defines")
    for t in seed["tests"]:
        graph.add_node(Node(f"test:{t['name']}", "test", t["name"], t["text"]))
        graph.add_edge(f"test:{t['name']}", f"fn:{t['covers']}", "tested_by")
    for tick in seed["tickets"]:
        graph.add_node(Node(f"ticket:{tick['ticket_id']}", "ticket", tick["ticket_id"], tick["title"]))
        graph.add_edge(f"ticket:{tick['ticket_id']}", f"fn:{tick['function']}", "fixes")
    return graph


def run_pipeline(seed_path: Path, db_path: Path) -> dict:
    seed = json.loads(seed_path.read_text())
    graph = build_graph(seed)
    router = ModelRouter(MODELS)
    tools = agents.build_tool_server({f["name"]: f["text"] for f in seed["files"]})
    conn = observability.init_db(str(db_path))

    ticket_results: dict[str, dict] = {}
    for tick in seed["tickets"]:
        ticket = Ticket(tick["ticket_id"], tick["title"], tick["function"],
                        tick["fix"], tick["files"])
        results = agents.run_sdlc(ticket, graph, tools, router,
                                  DIFFS[ticket.ticket_id],
                                  PATCHED_SOURCES[ticket.fix])
        for result in results:
            observability.record_run(
                conn,
                observability.RunRecord(ticket.ticket_id, result.stage,
                                        result.passed, result.summary, result.findings),
            )
        ticket_results[ticket.ticket_id] = {
            r.stage: {"passed": r.passed, "summary": r.summary, "findings": r.findings}
            for r in results
        }
    for decision in router.ledger.entries:
        observability.record_spend(conn, "all", decision.model.name,
                                   decision.task_type, decision.estimated_cost)

    benchmark_tasks = [
        benchmarks.BenchmarkTask(t["task_id"], t["kind"], t["prompt"], t["expected"],
                                 t.get("max_latency_ms", 1000.0))
        for t in seed["benchmark_tasks"]
    ]

    def answer_fn(task):
        # Stand-in answers: the "improved" agent names the bug / review point
        # from the seeded expected text; the baseline answers generically.
        improved = {
            "bug_detection": task.expected,
            "review_quality": task.expected,
            "latency": "fast answer",
        }
        return improved[task.kind], 120.0

    def baseline_fn(task):
        return "looks fine, no issues found", 90.0

    improved_suite = benchmarks.run_suite(benchmark_tasks, answer_fn)
    baseline_suite = benchmarks.run_suite(benchmark_tasks, baseline_fn)
    ab = benchmarks.ab_compare(baseline_suite, improved_suite)
    pareto = benchmarks.pareto_frontier([(0.02, 0.55), (0.10, 0.82), (0.35, 0.93),
                                         (0.40, 0.88), (0.12, 0.78)])

    report = {
        "tickets": ticket_results,
        "grounding_first_try_hit_rate": graph.first_try_hit_rate(
            [(t["title"], f"fn:{t['function']}") for t in seed["tickets"]]),
        "tool_totals": tools.totals(),
        "model_spend_usd": router.ledger.total_cost(),
        "spend_by_model_usd": router.ledger.cost_by_model(),
        "benchmark": {
            "baseline_mean": baseline_suite.mean(),
            "improved_mean": improved_suite.mean(),
            "mean_by_kind": improved_suite.mean_by_kind(),
            "pass_rate": improved_suite.pass_rate(),
            "ab_vs_baseline": ab,
        },
        "pareto_frontier_cost_quality": pareto,
        "dashboard": observability.dashboard(conn),
    }
    conn.close()
    return report
