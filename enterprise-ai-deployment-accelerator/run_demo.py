"""Demo: take a mid-market support-assistant use case from prototype
to a production-readiness verdict.

Seeds a small synthetic knowledge base, ranks two candidate use cases,
runs the eval suite, applies the readiness gate and writes a reusable
deployment playbook plus a JSONL observability log.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from enterprise_ai_deployment import (  # noqa: E402
    Agent, DocStore, Document, EvalCase, ReadinessGate,
    build_enterprise_tools, evaluate_readiness, generate_playbook,
    rank_use_cases, run_eval, UseCase,
)

DOCS = [
    Document("POL-001", "Password Reset Policy",
             "Employees reset passwords through the self-service portal. "
             "A reset link expires after 30 minutes. IT never asks for a "
             "password by email or phone."),
    Document("POL-002", "VPN Access Policy",
             "Remote access requires VPN with multi-factor authentication. "
             "VPN sessions time out after 12 hours and must be re-authenticated."),
    Document("POL-003", "Expense Reimbursement Policy",
             "Expenses under 75 dollars need only a receipt. Expenses of "
             "75 dollars or more need a receipt and manager approval. "
             "Reimbursement is paid within 10 business days."),
    Document("POL-004", "PTO Request Policy",
             "Time off requests need manager approval at least 5 business "
             "days in advance. Unused PTO carries over up to 5 days per year."),
    Document("POL-005", "Hardware Replacement Policy",
             "A laptop is replaced when it is older than 3 years or has a "
             "hardware fault confirmed by IT. Loaner laptops are issued "
             "within 1 business day."),
]

CASES = [
    EvalCase("c1", "How do I reset my password?",
             ["self-service portal", "30 minutes"]),
    EvalCase("c2", "What do I need for VPN access?",
             ["VPN", "multi-factor authentication"]),
    EvalCase("c3", "How long does expense reimbursement take?",
             ["10 business days", "receipt"]),
    EvalCase("c4", "How far in advance do I request time off?",
             ["5 business days", "manager approval"]),
    EvalCase("c5", "When is a laptop replaced?",
             ["3 years", "hardware fault"]),
    # A question with no grounding document (e.g. flight refunds) would
    # escalate to a human and fail the gate; it is covered in the tests,
    # not in the demo, so the demo shows a passing deployment.
]


def main() -> int:
    store = DocStore()
    for doc in DOCS:
        store.add(doc)
    registry = build_enterprise_tools(store)
    agent = Agent(store, registry)

    use_cases = [
        UseCase("Support knowledge assistant", "IT support",
                "Answer employee questions from policy documents with "
                "citations, escalating anything ungrounded.",
                value=8, data_readiness=9, risk=3,
                stakeholders=["IT", "HR"]),
        UseCase("Contract clause summariser", "Legal",
                "Summarise vendor contracts and flag unusual clauses.",
                value=7, data_readiness=4, risk=8,
                stakeholders=["Legal"]),
    ]
    ranked = rank_use_cases(use_cases)
    chosen = ranked[0]["use_case"]
    print(f"Chosen use case: {chosen.name} "
          f"(score {ranked[0]['score']}, tier {ranked[0]['tier']})")

    results, summary = run_eval(agent, CASES, log_path="evaluation_log.jsonl")
    for result in results:
        status = "PASS" if result.grade.passed else "FAIL"
        print(f"[{status}] {result.case_id}: {result.question} "
              f"(correctness {result.grade.correctness}, "
              f"grounding {result.grade.grounding})")
    print(f"Pass rate {summary.pass_rate:.0%} "
          f"({summary.passed}/{summary.total}), "
          f"p95 latency {summary.p95_latency_ms} ms, "
          f"cost ${summary.total_cost_usd:.4f}, "
          f"PII leaks {summary.pii_leaks}")

    report = evaluate_readiness(summary, ReadinessGate())
    for check in report.checks:
        print(f"[{'PASS' if check['passed'] else 'FAIL'}] "
              f"{check['name']}: {check['detail']}")
    playbook = generate_playbook(chosen, summary, report, ranked)
    Path("playbook.md").write_text(playbook, encoding="utf-8")
    print("Wrote playbook.md and evaluation_log.jsonl")
    print("Readiness:", "READY" if report.passed else "NOT READY")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
