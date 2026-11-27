"""Benchmark KG-RAG against the text-only baseline and write the report."""

from kg_rag.corpus import DOCUMENTS, QUESTIONS
from kg_rag.evaluate import benchmark, report_text
from kg_rag.graph import KnowledgeGraph
from kg_rag.retrieval import TfidfRanker


def main():
    graph = KnowledgeGraph.build(DOCUMENTS)
    ranker = TfidfRanker(DOCUMENTS)
    result = benchmark(DOCUMENTS, QUESTIONS, graph, ranker)
    text = report_text(result)
    print(text)
    with open("evaluation_report.txt", "w") as f:
        f.write(text)


if __name__ == "__main__":
    main()
