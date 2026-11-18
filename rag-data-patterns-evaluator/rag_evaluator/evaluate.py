"""Run every chunking strategy over every query and report precision/recall.

Usage:  python -m rag_evaluator.evaluate
Writes evaluation_report.txt next to this file's package and prints a summary.
"""

import json
from pathlib import Path

from .chunking import chunk_corpus
from .corpus import DOCS, QUERIES
from .retrieval import build_index, precision_at_k, recall_at_k, search

K = 3
REPORT_PATH = Path(__file__).resolve().parent.parent / "evaluation_report.txt"


def run_evaluation(k=K):
    """Return {strategy: {mean_precision@k, mean_recall@k, per_query: [...]}}."""
    results = {}
    for strategy in ("fixed", "sentence", "sliding"):
        chunks = chunk_corpus(DOCS, strategy)
        vocab, idf = build_index(chunks)
        per_query, precisions, recalls = [], [], []
        for query in QUERIES:
            hits = search(query["text"], chunks, vocab, idf, k=k)
            doc_ids = []
            for chunk, _ in hits:
                if chunk["doc_id"] not in doc_ids:
                    doc_ids.append(chunk["doc_id"])
            precision = precision_at_k(doc_ids, query["relevant"], k)
            recall = recall_at_k(doc_ids, query["relevant"])
            precisions.append(precision)
            recalls.append(recall)
            per_query.append(
                {
                    "query": query["id"],
                    "retrieved_docs": doc_ids,
                    "precision": round(precision, 3),
                    "recall": round(recall, 3),
                }
            )
        results[strategy] = {
            f"mean_precision@{k}": round(sum(precisions) / len(precisions), 3),
            f"mean_recall@{k}": round(sum(recalls) / len(recalls), 3),
            "chunks": len(chunks),
            "per_query": per_query,
        }
    return results


def format_report(results, k=K):
    lines = [
        "RAG DATA PATTERNS EVALUATOR — REPORT",
        f"Corpus: {len(DOCS)} documents, {len(QUERIES)} queries, top-{k} retrieval",
        "",
    ]
    for strategy, data in results.items():
        lines.append(
            f"{strategy}: chunks={data['chunks']} "
            f"mean_precision@{k}={data[f'mean_precision@{k}']} "
            f"mean_recall@{k}={data[f'mean_recall@{k}']}"
        )
        for row in data["per_query"]:
            lines.append(
                f"  {row['query']}: retrieved={','.join(row['retrieved_docs'])} "
                f"precision={row['precision']} recall={row['recall']}"
            )
    best = max(
        results,
        key=lambda s: (results[s][f"mean_recall@{k}"], results[s][f"mean_precision@{k}"]),
    )
    lines.append("")
    lines.append(f"Best mean recall@{k}: {best}")
    return "\n".join(lines) + "\n"


def main():
    results = run_evaluation()
    report = format_report(results)
    REPORT_PATH.write_text(report)
    print(report)
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
