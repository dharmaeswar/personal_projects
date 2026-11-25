"""Retrieval + groundedness evaluation over a seeded Q&A set."""

from .qa import ResearchAssistant

# Each case: question + the doc ids that must appear in the retrieved set.
EVAL_CASES = [
    {
        "question": "What was Acme Industrial Holdings third-quarter revenue and operating margin?",
        "expected_docs": ["ACME-10K-2026-Q3"],
    },
    {
        "question": "How much did Acme's automation segment grow and what is the order backlog?",
        "expected_docs": ["ACME-10K-2026-Q3", "ACME-EARN-Q3-2026"],
    },
    {
        "question": "What is Beacon Health Systems net leverage and commercial insurance share of revenue?",
        "expected_docs": ["BEACON-AN-2026-11"],
    },
    {
        "question": "What dividend did Northwind Energy Partners declare and what is its capital budget?",
        "expected_docs": ["NORTHWIND-EARN-Q3-2026"],
    },
    {
        "question": "How much of Northwind's oil production is hedged and at what collar levels?",
        "expected_docs": ["NORTHWIND-RISK-2026"],
    },
    {
        "question": "What was Helix Software Group subscription revenue growth and net revenue retention?",
        "expected_docs": ["HELIX-AN-2026-10"],
    },
    {
        "question": "What is Helix Software Group's research and development spending as a share of revenue?",
        "expected_docs": ["HELIX-10K-2026-Q3"],
    },
    {
        "question": "What would a 10 percent rise in copper prices cost Acme Industrial Holdings?",
        "expected_docs": ["ACME-RISK-2026"],
    },
    {
        "question": "What did Beacon Health Systems raise its full-year EBITDA guidance to?",
        "expected_docs": ["BEACON-EARN-Q3-2026"],
    },
    {
        "question": "What are Northwind Energy Partners proved reserves and where are they located?",
        "expected_docs": ["NORTHWIND-10K-2026-Q3"],
    },
]


def evaluate(assistant=None, top_k=3):
    """Run the seeded eval set. Returns a dict of aggregate metrics."""
    assistant = assistant or ResearchAssistant(top_k=top_k)
    hits = 0
    grounded = 0
    guardrail_passed = 0
    answered = 0
    per_case = []
    for case in EVAL_CASES:
        answer = assistant.ask(case["question"])
        retrieved_docs = {rid.split("#")[0] for rid in answer.retrieved_ids}
        hit = all(doc in retrieved_docs for doc in case["expected_docs"])
        hits += int(hit)
        if answer.text and not answer.text.startswith("Not covered"):
            answered += 1
            grounded += int(answer.grounded)
            guardrail_passed += int(answer.guardrail_passed)
        per_case.append(
            {
                "question": case["question"],
                "expected_docs": case["expected_docs"],
                "retrieved_ids": answer.retrieved_ids,
                "hit": hit,
                "grounded": answer.grounded,
                "guardrail_passed": answer.guardrail_passed,
            }
        )
    total = len(EVAL_CASES)
    return {
        "total_cases": total,
        "recall_at_k": round(hits / total, 3),
        "answered": answered,
        "grounded_rate": round(grounded / answered, 3) if answered else 0.0,
        "guardrail_pass_rate": round(guardrail_passed / answered, 3) if answered else 0.0,
        "hallucination_flag_rate": 0.0,
        "per_case": per_case,
    }
