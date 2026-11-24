"""Run one question through the multi-agent RAG pipeline.

Usage: python run_pipeline.py "What is Northgate Logistics Group's leverage ratio?"
Writes pipeline_report.txt next to this file.
"""

import sys

from bank_rag.pipeline import format_report, run_question

QUESTION = " ".join(sys.argv[1:]) or "What is Northgate Logistics Group's leverage ratio?"

if __name__ == "__main__":
    result = run_question(QUESTION)
    report = format_report(result)
    print(report)
    with open("pipeline_report.txt", "w") as handle:
        handle.write(report + "\n")
