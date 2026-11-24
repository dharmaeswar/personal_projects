"""Pipeline: plan -> retrieve -> context-engineer -> analyse -> validate.

One question in, one report dict out. Deterministic: same question, same
report, every run.
"""

from .agents import Analyst, Planner, Retriever, Validator
from .corpus import build_corpus


def run_question(question, docs=None, budget_chars=1200):
    docs = docs if docs is not None else build_corpus()
    planner = Planner()
    retriever = Retriever(docs)
    analyst = Analyst()
    validator = Validator()

    plan = planner.plan(question)
    retrieval = retriever.retrieve(question, budget_chars=budget_chars)
    result = analyst.answer(question, retrieval["context"], plan)
    check = validator.validate(result["answer"], retrieval["context"],
                               result["computed"], plan)
    return {
        "question": question,
        "plan": plan,
        "retrieved_doc_ids": [r["doc_id"] for r in retrieval["retrieved"]],
        "context": retrieval["context"],
        "answer": result["answer"],
        "citations": result["citations"],
        "computed": result["computed"],
        "validation": check,
    }


def format_report(result):
    lines = [
        f"Q: {result['question']}",
        f"Plan: {', '.join(result['plan']['subtasks'])}",
        f"Retrieved: {', '.join(result['retrieved_doc_ids'])}",
        f"Context: {result['context']['chars_used']} chars, "
        f"{len(result['context']['chunks'])} chunks, "
        f"truncated={result['context']['truncated']}",
        f"A: {result['answer']}",
        f"Citations: {', '.join(result['citations'])}",
        f"Validation: {result['validation']['verdict']}",
    ]
    for finding in result["validation"]["findings"]:
        lines.append(f"  Finding: {finding}")
    return "\n".join(lines)
