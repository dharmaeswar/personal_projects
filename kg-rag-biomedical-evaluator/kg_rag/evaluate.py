"""Evaluation & benchmarking: KG-RAG vs a text-only TF-IDF baseline.

Metrics per question: recall@k and precision@k against the known relevant
documents, and answer groundedness (fraction of claims cited to a
retrieved passage). The harness runs both systems on the same questions
so the comparison is fair; results are deterministic and reproducible.
"""

from .qa import answer, groundedness
from .retrieval import retrieve


def evaluate_one(question, documents, retrieved_ids):
    relevant = set(question["relevant"])
    retrieved = retrieved_ids[:3]
    hits = len(set(retrieved) & relevant)
    recall = hits / len(relevant) if relevant else 1.0
    precision = hits / len(retrieved) if retrieved else 0.0
    result = answer(question["question"], documents, retrieved)
    ground = groundedness(result, set(retrieved))
    expected = set(question.get("expected_entities", set()))
    found = set()
    for claim in result["claims"]:
        for ent in expected:
            if ent.lower() in claim["text"].lower():
                found.add(ent)
    completeness = len(found) / len(expected) if expected else 1.0
    return {
        "question_id": question["id"],
        "retrieved": retrieved,
        "relevant": sorted(relevant),
        "recall@3": round(recall, 3),
        "precision@3": round(precision, 3),
        "groundedness": round(ground, 3),
        "completeness": round(completeness, 3),
        "abstained": result["abstained"],
    }


def _mean(rows, key):
    return round(sum(r[key] for r in rows) / len(rows), 3) if rows else 0.0


def benchmark(documents, questions, graph, ranker):
    """Run KG-RAG and the text-only baseline over the same questions."""
    kg_rows, base_rows = [], []
    for q in questions:
        kg_rows.append(evaluate_one(
            q, documents, retrieve(graph, ranker, q["question"], k=3)))
        base_rows.append(evaluate_one(
            q, documents, ranker.top_k(q["question"], k=3)))
    summary = {}
    for name, rows in (("kg_rag", kg_rows), ("text_only", base_rows)):
        summary[name] = {
            "recall@3": _mean(rows, "recall@3"),
            "precision@3": _mean(rows, "precision@3"),
            "groundedness": _mean(rows, "groundedness"),
            "completeness": _mean(rows, "completeness"),
            "abstentions": sum(1 for r in rows if r["abstained"]),
        }
    return {"per_question": {"kg_rag": kg_rows, "text_only": base_rows},
            "summary": summary}


def report_text(benchmark_result):
    lines = ["KG-RAG vs text-only TF-IDF baseline (8 seeded questions)",
             "-" * 62]
    s = benchmark_result["summary"]
    lines.append(f"{'metric':<16}{'KG-RAG':>10}{'text-only':>12}{'delta':>10}")
    for key in ("recall@3", "precision@3", "groundedness", "completeness"):
        delta = round(s["kg_rag"][key] - s["text_only"][key], 3)
        lines.append(f"{key:<16}{s['kg_rag'][key]:>10.3f}{s['text_only'][key]:>12.3f}{delta:>10.3f}")
    lines.append(f"{'abstentions':<16}{s['kg_rag']['abstentions']:>10}"
                 f"{s['text_only']['abstentions']:>12}")
    lines.append("")
    lines.append("Per-question recall@3 (KG-RAG vs text-only):")
    for kg, base in zip(benchmark_result["per_question"]["kg_rag"],
                        benchmark_result["per_question"]["text_only"]):
        lines.append(f"  {kg['question_id']}: {kg['recall@3']:.3f} vs {base['recall@3']:.3f}"
                     f"  retrieved={kg['retrieved']} relevant={kg['relevant']}")
    return "\n".join(lines) + "\n"
