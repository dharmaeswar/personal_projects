"""Build the knowledge graph, answer the evaluation questions, write outputs."""

import json

from kg_rag.corpus import DOCUMENTS, QUESTIONS
from kg_rag.graph import KnowledgeGraph
from kg_rag.qa import answer
from kg_rag.retrieval import TfidfRanker, retrieve


def main():
    graph = KnowledgeGraph.build(DOCUMENTS)
    ranker = TfidfRanker(DOCUMENTS)
    with open("graph_summary.json", "w") as f:
        json.dump(graph.summary(), f, indent=2)
    results = []
    for q in QUESTIONS:
        retrieved = retrieve(graph, ranker, q["question"], k=3)
        result = answer(q["question"], DOCUMENTS, retrieved)
        results.append({"question_id": q["id"], "question": q["question"],
                        "retrieved": retrieved, "answer": result["answer"],
                        "abstained": result["abstained"]})
        print(f"{q['id']}: retrieved={retrieved}")
        print(result["answer"])
        print()
    with open("answers.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Graph:", json.dumps(graph.summary()))


if __name__ == "__main__":
    main()
