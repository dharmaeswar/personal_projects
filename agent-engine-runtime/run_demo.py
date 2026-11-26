"""Demo: run the seeded support agent and print the trace.

    python run_demo.py
"""

from agent_engine.cli import build_engine


def main() -> None:
    engine = build_engine()
    result = engine.run("demo", context={"question": "refund policy"})
    print(f"agent: {result.agent_name}  status: {result.status}  "
          f"elapsed: {result.elapsed_seconds:.3f}s")
    for step in result.steps:
        print(f"  - {step.name}: {step.status} "
              f"(attempts={step.attempts}) -> {step.value!r}")
    print("\nMemory context block for 'refund policy':")
    print(engine.memory.context_block("refund policy"))
    print("\nGovernance audit log:")
    for entry in engine.policies.audit_log:
        print(f"  - {entry['tool']} by {entry['principal']}: "
              f"{'ALLOWED' if entry['allowed'] else 'DENIED'} "
              f"({entry['reason']})")


if __name__ == "__main__":
    main()
