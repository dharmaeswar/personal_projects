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

## AI knowledge platform service (added Nov 23, 2026)

The evaluator's chunking and retrieval now also power a small
knowledge-ingestion service — the same shape as an enterprise AI
platform's knowledge-and-retrieval layer: ingest documents, index
them in a vector store, and serve ranked retrieval through an API
with citations and observability hooks.

```python
from rag_evaluator.api import KnowledgeRetrievalAPI
from rag_evaluator.corpus import DOCS

api = KnowledgeRetrievalAPI(api_key="demo-key")
api.ingest_documents(DOCS)  # 10 docs -> 15 chunks (sentence strategy)
response = api.retrieve(
    "how do Kafka streams move usage events in real time",
    k=3, api_key="demo-key",
)
# response["results"][0]: kafka-streaming#chunk-0, score 0.5134
```

- `rag_evaluator/ingestion.py` — `KnowledgeIngestionPipeline`:
  validates each document (bad docs are rejected with a reason, never
  failing the batch), chunks it with a chosen strategy, embeds the
  chunks and upserts them into the store, with a telemetry span per
  stage (validate / chunk / embed-upsert).
- `rag_evaluator/vector_store.py` — `VectorStore`: in-memory chunk
  embeddings with upsert, ranked cosine search, and JSON save/load.
- `rag_evaluator/api.py` — `KnowledgeRetrievalAPI`: `ingest_documents`
  plus `retrieve`, which returns ranked chunks with citations
  (`doc_id#chunk-N`), scores and a per-request trace id, behind a
  simple API-key check (a local stand-in for gateway OAuth/OIDC/Okta,
  not production auth), plus a `health()` check.
- `rag_evaluator/observability.py` — `Telemetry`: spans, events and
  counters in the OpenTelemetry shape, exportable as JSON lines for a
  log aggregator such as Splunk.

## Test it

```bash
python -m pytest -q
```

## Layout

- `rag_evaluator/corpus.py` — synthetic documents and queries with ground truth
- `rag_evaluator/chunking.py` — fixed, sentence, and sliding-window chunkers
- `rag_evaluator/retrieval.py` — TF-IDF vectors, cosine search, precision/recall
- `rag_evaluator/evaluate.py` — runs every strategy over every query, writes the report
- `rag_evaluator/ingestion.py` — knowledge-ingestion pipeline (validate, chunk, embed, upsert)
- `rag_evaluator/vector_store.py` — in-memory vector store with search and JSON save/load
- `rag_evaluator/api.py` — retrieval API with citations, trace ids and an API-key check
- `rag_evaluator/observability.py` — spans, events and counters (OpenTelemetry shape)
- `tests/` — pytest tests for chunking invariants, retrieval maths, evaluation, ingestion, vector store, API and observability

## Notes

- Everything is deterministic: same input, same scores, every run.
- The ranker is a TF-IDF baseline, not a neural embedding model — it measures
  chunking quality, not embedding-model quality. A real embedding model can
  replace `retrieval.embed` without changing the evaluation harness.
- No cloud services, no production data, no credentials needed.
