# Knowledge-Graph RAG for Biomedical Literature — Evaluator

A knowledge-graph-backed retrieval-augmented generation (RAG) pipeline over
synthetic biomedical literature, built as a portfolio project for a
Regeneron AI Engineer II application: knowledge graphs and the data
pipelines that support them, LLM-based retrieval and content-generation
tools, and model/AI-system evaluation and benchmarking.

**Honest note:** all documents, genes, drugs, diseases and relations are
synthetic and invented for this demo. No real patient data, no real
Regeneron data, no real literature is used, and there are no live LLM or
API calls: entity/relation extraction is deterministic rule-based code over
seeded text, and the answer composer is a deterministic extractive
stand-in that only repeats what the retrieved passages say. A real LLM
(for example a Hugging Face / PyTorch model or an API model) plugs into
the same `retrieve -> compose` interfaces, and its drafts would go through
the same groundedness checks. This is a demo built to show the
architecture and the evaluation, not a claim of real biomedical research.

## The problem

A scientist's question mixes kinds of evidence. "Which drug targets
BRCA1-mutated breast cancer?" needs a drug–gene relation AND a
gene–disease relation, and the answer must name both links. A plain
keyword search ranks the document that mentions the drug most often and
drops the gene–disease link; an LLM answering from memory invents a
drug–gene pair that was never published. This pipeline builds a knowledge
graph from the documents, retrieves by walking the graph from the
entities in the question, fuses that with text retrieval, and composes an
answer only from retrieved evidence, with a citation on every claim.

## What it does

- **Data pipeline** (`kg_rag/corpus.py`, `kg_rag/graph.py`) — 15 seeded
  biomedical documents (12 evidence documents plus 3 screening/awareness
  distractors that share vocabulary but hold no drug–gene relation);
  deterministic entity/relation extraction builds a
  typed knowledge graph (Gene, Protein, Disease, Drug, Pathway nodes;
  TARGETS, TREATS, ASSOCIATED_WITH, INTERACTS_WITH, PART_OF edges) with
  source-document provenance on every edge.
- **Retrieval** (`kg_rag/retrieval.py`) — 2-hop graph traversal from the
  entities in the question, fused with TF-IDF text retrieval over the
  passages. Graph neighbours supply the structured evidence; text
  retrieval supplies the wording.
- **Grounded generation** (`kg_rag/qa.py`) — extractive answer composer:
  every claim in the answer comes from a retrieved passage and carries a
  citation `[doc-id]`; when nothing retrieved is relevant it says so
  instead of inventing an answer.
- **Evaluation & benchmarking** (`kg_rag/evaluate.py`) — 8 seeded
  questions with known relevant documents; reports retrieval recall@3
  and precision@3, answer groundedness (fraction of claims with a
  citation to a supporting passage), and abstention behaviour, for
  KG-RAG versus a text-only TF-IDF baseline on the same questions.
- **Human-in-the-loop feedback** (`kg_rag/feedback.py`) — accept/reject
  feedback on answers is logged, down-weights edges behind rejected
  answers and up-weights edges behind accepted ones, and re-ranks
  retrieval on the next run. Feedback is an audit trail, not a silent
  override: every change is recorded with the question and the reason.
- **Bioassay knowledge graph** (`kg_rag/bioassay.py`, added Nov 28, 2026
  for an AbbVie Associate Data Scientist II application) — seeded
  synthetic bioassay results are validated (positive IC50, >= 2
  replicates, Z-prime in range) and cleaned; 2 of 16 seeded rows are
  rejected. Clean rows load into SQLite tables (`assays`,
  `bioassay_results`) with a `v_potent_compounds` view (IC50 < 100 nM,
  QC passed) and reporting queries (median IC50 per target, hit rate
  per assay type, QC summary). Each assay becomes an Assay node in the
  graph — compound -TESTED_IN-> assay -MEASURES-> target gene/protein —
  so a scientist can walk from a compound to its target through the
  assay. A static HTML dashboard (`dashboard.html`) and CSV report
  (`bioassay_report.csv`) present the same queries. Run with
  `python run_bioassay.py`. Results on the seeded data: 14 clean rows,
  7 potent compounds, QC pass rate 0.857, median IC50 3.6 nM (BRAF),
  10.2 nM (EGFR), 48.5 nM (BRCA1).
- **Responsible AI** — synthetic data only, provenance on every edge and
  claim, an audit log of feedback and evaluations, and an explicit
  "not covered by the documents" abstention path.

## Run it

```bash
python run_pipeline.py      # build the graph, answer the 8 eval questions
python run_evaluation.py    # benchmark KG-RAG vs text-only baseline
python run_bioassay.py      # bioassay ETL -> SQLite -> graph -> dashboard
python -m pytest -q         # 42 tests
```

`run_pipeline.py` writes `graph_summary.json` and `answers.json`.
`run_evaluation.py` writes `evaluation_report.txt` and prints the
comparison table.

## Results (seeded synthetic corpus, Nov 27, 2026)

| system | recall@3 | precision@3 | groundedness | completeness |
|---|---|---|---|---|
| text-only TF-IDF | 0.917 | 0.500 | 1.000 | 0.844 |
| KG-RAG (graph + TF-IDF) | 1.000 | 0.583 | 1.000 | 0.958 |

Graph traversal recovers the second hop (drug -> gene -> disease) that
text ranking misses: on Q3 ("which drugs treat breast cancer, and which
genes do they target?") the text-only ranker is fooled by a screening
document that shares the words "breast cancer" but holds no drug–gene
relation, and retrieves only 1 of the 3 relevant documents (recall@3
0.333); KG-RAG retrieves all 3. Groundedness is 1.000 in both cases
because every claim must carry a citation to a retrieved passage. See
`evaluation_report.txt` for the per-question breakdown.

## Files

- `kg_rag/corpus.py` — seeded synthetic documents and the question set
- `kg_rag/graph.py` — entity/relation extraction and the knowledge graph
- `kg_rag/retrieval.py` — TF-IDF ranker, graph traversal, fused retrieval
- `kg_rag/qa.py` — grounded extractive answer composer
- `kg_rag/evaluate.py` — benchmark harness (KG-RAG vs text-only)
- `kg_rag/feedback.py` — human-in-the-loop feedback and edge reweighting
- `kg_rag/bioassay.py` — bioassay ETL, SQLite warehouse, graph extension, dashboard
- `run_pipeline.py`, `run_evaluation.py`, `run_bioassay.py` — entry points
- `tests/` — pytest suite (42 tests)
