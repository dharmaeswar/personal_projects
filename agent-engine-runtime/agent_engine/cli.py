"""Developer CLI for the agent engine runtime.

Usage:
    python -m agent_engine.cli list-tools
    python -m agent_engine.cli list-agents
    python -m agent_engine.cli run demo --question "refund policy"
    python -m agent_engine.cli recall "refund policy"
    python -m agent_engine.cli search "refund policy"
"""

from __future__ import annotations

import argparse
import json

from .governance import Policy
from .retrieval import Document
from .sdk import Engine, demo_agent_steps

SEEDED_DOCS = [
    Document(doc_id="kb-refund-policy",
             text="Refund policy: orders can be refunded within 30 days of "
                  "purchase when the item is unused and in its packaging.",
             kind="knowledge"),
    Document(doc_id="kb-shipping-sla",
             text="Shipping SLA: standard delivery takes 3 to 5 business days; "
                  "express delivery takes 1 to 2 business days.",
             kind="knowledge"),
    Document(doc_id="runbook-incident",
             text="Incident runbook: acknowledge the alert, check the status "
                  "page, roll back the last deploy, then page on-call.",
             kind="runbook"),
]


def build_engine() -> Engine:
    engine = Engine(tenant_id="tenant-demo", principal="agent:support-bot",
                    scopes=["tools:calc", "tools:read"])
    engine.grant(Policy(name="allow-calc", effect="allow", tool="calculator"))
    engine.grant(Policy(name="allow-echo", effect="allow", tool="echo"))
    engine.grant(Policy(name="deny-export", effect="deny", tool="export_data"))
    for doc in SEEDED_DOCS:
        engine.add_knowledge(doc)
    engine.memory.remember(
        "Customer asked about the refund policy for order 1042.")
    engine.memory.remember(
        "Agent confirmed the 30 day refund window applies to order 1042.")
    engine.register_agent("demo", demo_agent_steps(engine))
    return engine


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="agent-engine",
                                     description="Agent Engine Runtime CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-tools", help="list registered tools")
    sub.add_parser("list-agents", help="list registered agents")
    run_p = sub.add_parser("run", help="run a registered agent")
    run_p.add_argument("agent")
    run_p.add_argument("--question", default="refund policy")
    recall_p = sub.add_parser("recall", help="recall session history")
    recall_p.add_argument("query")
    search_p = sub.add_parser("search", help="search the knowledge index")
    search_p.add_argument("query")
    args = parser.parse_args(argv)

    engine = build_engine()
    if args.command == "list-tools":
        print("\n".join(engine.tools.tool_names()))
    elif args.command == "list-agents":
        print("\n".join(engine.agent_names()))
    elif args.command == "run":
        result = engine.run(args.agent, context={"question": args.question})
        print(json.dumps({
            "agent": result.agent_name, "status": result.status,
            "steps": [{"name": s.name, "status": s.status,
                       "value": s.value, "attempts": s.attempts}
                      for s in result.steps],
        }, indent=2))
    elif args.command == "recall":
        for hit in engine.recall(args.query):
            print(f"{hit.score:.2f}  {hit.episode.text}")
    elif args.command == "search":
        for hit in engine.search(args.query):
            print(f"{hit.score:.2f}  {hit.document.doc_id}: {hit.document.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
