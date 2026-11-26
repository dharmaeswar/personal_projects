"""Evaluation harness: scripted marketing questions with expected citations.

Metrics
- retrieval precision@3: share of the top 3 retrieved docs that are in the
  expected set for the question.
- citation coverage: share of questions whose expected documents all appear
  in the top 5 retrieved docs.
- faithfulness: share of answers that pass ValidatorAgent (every number in
  the answer appears in the retrieved documents).

Run: python -m marketing_rag.evaluation  (or POST /evaluate)
"""
from __future__ import annotations

EVAL_CASES = [
    {"question": "Which campaign has the best return on spend?",
     "expected": {"CMP-007", "CMP-005"}},
    {"question": "What is the CPA of the Display Retargeting campaign?",
     "expected": {"CMP-005"}},
    {"question": "Which audience segment should the LinkedIn ABM pilot target?",
     "expected": {"SEG-002", "CMP-003"}},
    {"question": "What content asset fits the spring email launch?",
     "expected": {"AST-002", "CMP-001"}},
    {"question": "How large is the small business owners segment?",
     "expected": {"SEG-003"}},
    {"question": "Which webinar content do we have for lead follow-up?",
     "expected": {"AST-005", "AST-010", "CMP-004"}},
    {"question": "Where should we move budget from the weakest campaign?",
     "expected": {"CMP-005", "CMP-007"}},
    {"question": "What guide helps buyers compare marketing automation platforms?",
     "expected": {"AST-001", "CMP-008"}},
]


def run_evaluation(service) -> dict:
    results = []
    for case in EVAL_CASES:
        answer = service.ask(case["question"], top_k=5)
        top3 = {c["id"] for c in answer["citations"][:3]}
        top5 = {c["id"] for c in answer["citations"]}
        expected = case["expected"]
        precision_at_3 = len(top3 & expected) / max(len(top3), 1)
        covered = expected.issubset(top5)
        results.append({
            "question": case["question"],
            "expected": sorted(expected),
            "retrieved_top3": sorted(top3),
            "precision_at_3": round(precision_at_3, 2),
            "covered_in_top5": covered,
            "validator_passed": answer["validation"]["passed"],
        })
    n = len(results)
    report = {
        "cases": n,
        "mean_precision_at_3": round(sum(r["precision_at_3"] for r in results) / n, 2),
        "citation_coverage": round(sum(r["covered_in_top5"] for r in results) / n, 2),
        "faithfulness": round(sum(r["validator_passed"] for r in results) / n, 2),
        "results": results,
    }
    return report


if __name__ == "__main__":
    from .service import MarketingRagService

    report = run_evaluation(MarketingRagService())
    print(f"Cases: {report['cases']}")
    print(f"Mean precision@3: {report['mean_precision_at_3']}")
    print(f"Citation coverage (top 5): {report['citation_coverage']}")
    print(f"Faithfulness (validator pass rate): {report['faithfulness']}")
    for result in report["results"]:
        mark = "PASS" if result["covered_in_top5"] and result["validator_passed"] else "CHECK"
        print(f"[{mark}] p@3={result['precision_at_3']}  {result['question']}")
