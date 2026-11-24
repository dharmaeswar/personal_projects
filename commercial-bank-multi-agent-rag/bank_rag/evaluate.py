"""Seeded evaluation set for the multi-agent RAG pipeline.

Each case has the expected numeric answer (with tolerance), the expected
covenant verdict, or an expected phrase from the memo. Metrics: answer
accuracy, groundedness (validator PASS rate) and citation coverage.
"""

EVAL_CASES = [
    {
        "id": "E1",
        "question": "What is Northgate Logistics Group's leverage ratio?",
        "expected_number": 3.5,
        "tolerance": 0.01,
    },
    {
        "id": "E2",
        "question": "What is BlueRock Packaging Co's interest coverage ratio?",
        "expected_number": 2.0,
        "tolerance": 0.01,
    },
    {
        "id": "E3",
        "question": "What is Summit Ridge Manufacturing's EBITDA margin?",
        "expected_number": 12.5,
        "tolerance": 0.01,
    },
    {
        "id": "E4",
        "question": "Is BlueRock Packaging Co in compliance with its leverage covenant?",
        "expected_verdict": "in breach",
    },
    {
        "id": "E5",
        "question": "Is Northgate Logistics Group in compliance with its covenants?",
        "expected_verdict": "in compliance",
    },
    {
        "id": "E6",
        "question": "Which borrower has the highest EBITDA margin?",
        "expected_phrase": "BlueRock Packaging Co",
    },
    {
        "id": "E7",
        "question": "What does the credit memo say about Summit Ridge Manufacturing's supply-chain risk?",
        "expected_phrase": "single-source supplier",
    },
    {
        "id": "E8",
        "question": "What is BlueRock Packaging Co's leverage ratio?",
        "expected_number": 4.0,
        "tolerance": 0.01,
    },
]

NUMBER_RE = __import__("re").compile(r"\d+\.\d+|\d+")


def score_case(result, case):
    """Return (passed, detail) for one evaluated case."""
    answer = result["answer"]
    if "expected_number" in case:
        numbers = [float(n) for n in NUMBER_RE.findall(answer)]
        ok = any(abs(n - case["expected_number"]) <= case["tolerance"]
                 for n in numbers)
        return ok, f"expected {case['expected_number']}, got {numbers}"
    if "expected_verdict" in case:
        ok = case["expected_verdict"] in answer
        return ok, f"expected '{case['expected_verdict']}' in answer"
    if "expected_phrase" in case:
        ok = case["expected_phrase"].lower() in answer.lower()
        return ok, f"expected phrase '{case['expected_phrase']}'"
    return False, "case has no expectation"


def run_evaluation(docs=None):
    from .pipeline import run_question

    rows = []
    for case in EVAL_CASES:
        result = run_question(case["question"], docs=docs)
        passed, detail = score_case(result, case)
        grounded = result["validation"]["verdict"] == "PASS"
        cited = len(result["citations"]) > 0
        rows.append({
            "id": case["id"],
            "question": case["question"],
            "answer": result["answer"],
            "passed": passed,
            "detail": detail,
            "grounded": grounded,
            "cited": cited,
        })
    total = len(rows)
    return {
        "rows": rows,
        "accuracy": sum(r["passed"] for r in rows) / total,
        "groundedness": sum(r["grounded"] for r in rows) / total,
        "citation_coverage": sum(r["cited"] for r in rows) / total,
        "total": total,
    }


def format_evaluation_report(evaluation):
    lines = ["Multi-Agent RAG Evaluation",
             f"Cases: {evaluation['total']}",
             f"Answer accuracy: {evaluation['accuracy']:.2%}",
             f"Groundedness (validator PASS): {evaluation['groundedness']:.2%}",
             f"Citation coverage: {evaluation['citation_coverage']:.2%}",
             ""]
    for row in evaluation["rows"]:
        mark = "PASS" if row["passed"] else "FAIL"
        lines.append(f"{row['id']} [{mark}] {row['question']}")
        lines.append(f"  A: {row['answer']}")
        lines.append(f"  Check: {row['detail']}; grounded={row['grounded']}, cited={row['cited']}")
    return "\n".join(lines)
