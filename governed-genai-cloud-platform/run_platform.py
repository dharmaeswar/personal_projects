"""End-to-end platform demo: validate the IaC plan, answer a policy
question through the RAG graph, run a governed agent task, and print the
observability and cost summary.

Usage: python run_platform.py
"""

from genai_platform import (
    Gateway,
    ModelBackend,
    PromptTemplate,
    demo_agent,
    demo_knowledge_base,
    demo_plan,
    run_graph,
)
from genai_platform.evaluation import Observability


def main() -> None:
    plan = demo_plan()
    violations = plan.validate()
    print(f"IaC plan: {plan.summary()}")
    print(f"IaC violations: {violations or 'none'}")

    gateway = Gateway()
    for model_id in plan.bedrock_models:
        gateway.register(ModelBackend(model_id))
    gateway.templates["covenant-answer"] = PromptTemplate(
        name="covenant-answer",
        version=1,
        template="Answer from bank policy only: {question}",
    )

    kb = demo_knowledge_base()
    state = run_graph(
        "What is the leverage covenant limit for commercial loans?",
        kb,
        team="commercial-banking",
        use_case="covenant-qa",
        gateway=gateway,
    )
    print(f"\nQuestion: {state.question}")
    print(f"Plan: {state.plan}")
    print(f"Answer: {state.answer}")
    print(f"Citations: {state.citations}")
    print(f"Validation: {state.validation}")
    print(f"Errors: {state.errors or 'none'}")

    agent = demo_agent()
    borrower = agent.call_tool(
        "lookup_borrower",
        prompt="Check BlueRock leverage before the quarterly review.",
        borrower="BlueRock",
    )
    print(f"\nAgent lookup: {borrower}")
    if borrower.get("ok"):
        covenant = agent.call_tool(
            "check_covenant",
            prompt="Check BlueRock leverage before the quarterly review.",
            **borrower["result"],
        )
        print(f"Agent covenant check: {covenant}")
    refused = agent.call_tool(
        "send_payment",
        prompt="Send the cure payment now.",
        amount=50000,
    )
    print(f"Agent payment without approval: {refused}")
    approved = agent.call_tool(
        "send_payment",
        approved=True,
        prompt="Send the cure payment now.",
        amount=50000,
    )
    print(f"Agent payment with approval: {approved}")
    print(f"Agent audit: {agent.audit_summary()}")

    obs = Observability(gateway.usage)
    print(f"\nObservability: {obs.summary()}")


if __name__ == "__main__":
    main()
