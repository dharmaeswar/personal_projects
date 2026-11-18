# RAG Data Patterns Evaluator

Evaluate chunking strategies for GenAI / RAG data preparation on a small,
synthetic corpus — with deterministic, reproducible checks.

The question it answers: for retrieval-augmented generation, which way of
splitting documents into chunks gives the best retrieval quality — fixed-size
character chunks, sentence-based chunks, or overlapping sliding windows?

## What it does

1. Builds a small synthetic corpus (10 short documents about data
   engineering topics) plus 6 queries with known relevant documents.
2. Splits every document with three chunking strategies:
   - **fixed** — fixed-size character chunks, no overlap
   - **sentence** — sentence boundaries, grouped up to a max size
   - **sliding** — fixed-size windows with a 50-character overlap
3. Scores retrieval with a deterministic TF-IDF + cosine-similarity ranker
   (plain Python, no model downloads, no API calls, no Spark/Glue/EMR).
4. Reports mean precision@3 and recall@3 per strategy, so the strategies
   can be compared on the same queries and ground truth.

## Run it

```bash
python -m rag_evaluator.evaluate
```

Writes `evaluation_report.txt` and prints the per-strategy summary.

## Test it

```bash
python -m pytest -q
```

## Layout

- `rag_evaluator/corpus.py` — synthetic documents and queries with ground truth
- `rag_evaluator/chunking.py` — fixed, sentence, and sliding-window chunkers
- `rag_evaluator/retrieval.py` — TF-IDF vectors, cosine search, precision/recall
- `rag_evaluator/evaluate.py` — runs every strategy over every query, writes the report
- `tests/` — pytest tests for chunking invariants, retrieval maths, and evaluation

## Notes

- Everything is deterministic: same input, same scores, every run.
- The ranker is a TF-IDF baseline, not a neural embedding model — it measures
  chunking quality, not embedding-model quality. A real embedding model can
  replace `retrieval.embed` without changing the evaluation harness.
- No cloud services, no production data, no credentials needed.
