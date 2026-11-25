"""Demo runner: answer sample analyst questions, run the eval, write a report."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from research_assistant.evaluate import evaluate
from research_assistant.qa import ResearchAssistant

SAMPLE_QUESTIONS = [
    "What was Acme Industrial Holdings third-quarter revenue and operating margin?",
    "How much of Northwind's oil production is hedged and at what collar levels?",
    "What is Helix Software Group's research and development spending as a share of revenue?",
]


def main():
    assistant = ResearchAssistant()
    print("=== Investment Research AI Assistant — demo ===\n")
    for question in SAMPLE_QUESTIONS:
        answer = assistant.ask(question, log_path="research_queries.jsonl")
        print(f"Q: {question}")
        print(f"A: {answer.text}")
        print("Citations:")
        for citation in answer.citations:
            print(f"  - {citation}")
        print(f"Guardrails: {'PASS' if answer.guardrail_passed else 'FAIL'}")
        print()
    report = evaluate(assistant)
    report_path = "research_eval_report.json"
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print("=== Evaluation ===")
    print(f"Cases: {report['total_cases']}")
    print(f"Recall@3: {report['recall_at_k']}")
    print(f"Answered: {report['answered']}/{report['total_cases']}")
    print(f"Grounded rate: {report['grounded_rate']}")
    print(f"Guardrail pass rate: {report['guardrail_pass_rate']}")
    print(f"Hallucination flag rate: {report['hallucination_flag_rate']}")
    print(f"Report written to {report_path}")
    verdict = "PASS" if report["recall_at_k"] >= 0.8 and report["grounded_rate"] == 1.0 else "FAIL"
    print(f"Verdict: {verdict}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
