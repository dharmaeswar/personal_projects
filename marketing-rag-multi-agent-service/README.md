# Marketing RAG Multi-Agent Service

A retrieval-augmented generation service that answers marketing questions
over campaign, segment and content data — built for the HubSpot Senior AI
Engineer (AIMS — AI Marketing Solutions) application: RAG retrieval, vector
retrieval concepts, multi-agent workflows, REST APIs, data pipelines and
testing, against a marketing-technology (CRM/CDP) style corpus.

**Honest note:** all data is synthetic and generated locally with a fixed
seed (see `marketing_rag/corpus.py`). No real customers, campaigns or
performance figures are used. Retrieval is deterministic TF-IDF plus cosine
similarity in plain Python — **not** a vector database and **not** an
embedding model. The agents are deterministic rule-based policies — **not**
live LLM calls. A real LLM (for example LangChain or the OpenAI API) plugs
into the same `plan / retrieve / answer / validate` interfaces, and its
drafts would go through the same ValidatorAgent. This is a demo built to
show the architecture, not production marketing data and not a claim of real
marketing experience.

## The problem

A marketing question mixes kinds of evidence. "Which campaign has the best
return on spend?" needs exact figures (spend, conversions, revenue) to
compute ROI. "Which audience should the LinkedIn ABM pilot target?" needs
the CRM/CDP segment behind the campaign. "What content fits the spring
email launch?" needs the asset library. A plain keyword search ranks the
wrong document for at least one of those, and an LLM answering from memory
invents figures. This service plans the question, retrieves cited documents,
lets one agent per concern answer from that evidence only, and validates
every number in the answer against the cited documents before it ships.

## What it does

1. **Corpus** (`marketing_rag/corpus.py`) — 8 campaigns, 6 segments, 10
   content assets and 200 seeded CRM-like contacts, all synthetic. Campaign
   text carries spend, leads, conversions, revenue, CPA and ROI; segments
   carry size, criteria and CRM/CDP source; assets carry type, channel and
   campaign.
2. **Retrieval** (`marketing_rag/retrieval.py`) — TF-IDF + cosine similarity
   over 24 documents, with chunking that keeps every chunk tied to its
   source document id so a citation always points back to its source.
3. **Multi-agent workflow** (`marketing_rag/agents.py`) — PlannerAgent splits
   a question into subtasks by intent; AudienceAgent sizes matching
   segments (including segments linked from a retrieved campaign);
   ContentAgent picks the best content asset; BudgetAgent computes CPA/ROI
   over the full campaign table and suggests a reallocation from those
   figures only; ValidatorAgent checks every number in the draft answer
   against the cited documents and flags anything unsupported.
4. **Service** (`marketing_rag/service.py`) — `ask()` runs plan → retrieve →
   agents → validate → answer. The answer quotes only numbers that appear
   verbatim in the cited documents. Computed values (audience totals,
   reallocation amounts) are returned separately and marked derived, never
   quoted as retrieved facts. Citations list the documents the answer
   quotes first, then the rest of the retrieved set.
5. **REST API** (`marketing_rag/api.py`, standard library only) — `GET
   /health`, `GET /campaigns`, `POST /ask`, `POST /evaluate`.
6. **Evaluation harness** (`marketing_rag/evaluation.py`) — 8 scripted
   questions with expected citations; reports mean precision@3, citation
   coverage and faithfulness (validator pass rate).

## Results (seeded run)

- `python run_demo.py`:
  - "Which campaign has the best return on spend?" → Partner Co-Marketing
    at 5.50x ($12,000 spend, $66,000 revenue); weakest is Display
    Retargeting at 0.94x ($31,000 spend, $29,000 revenue). Validation
    passed, no unsupported numbers.
  - "Which audience segment should the LinkedIn ABM pilot target?" →
    Enterprise marketing VPs, 6,200 contacts (named accounts). Validation
    passed.
  - Derived suggestion: move 10% of Display Retargeting spend ($3,100) to
    Partner Co-Marketing; expected gain about $14,136 at the fitted ROI gap.
- `python -m marketing_rag.evaluation` — 8 cases: mean precision@3 0.58,
  citation coverage (top 5) 1.00, faithfulness 1.00.
- `pytest tests/` — **36 passed, 0 failed**.

## Run it

```bash
python run_demo.py            # ask three questions, print answers + citations
python run_server.py          # REST API on http://127.0.0.1:8000
python -m marketing_rag.evaluation
python -m pytest tests/ -q
```

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/campaigns
curl -X POST http://127.0.0.1:8000/ask \
  -H 'Content-Type: application/json' \
  -d '{"question": "Which campaign has the best return on spend?"}'
curl -X POST http://127.0.0.1:8000/evaluate
```

Or with Docker: `docker build -t marketing-rag . && docker run -p 8000:8000 marketing-rag`.

## Layout

```
marketing_rag/
  corpus.py      # seeded synthetic campaigns, segments, assets, contacts
  retrieval.py   # TF-IDF + cosine retrieval, chunking
  agents.py      # planner, audience, content, budget, validator agents
  service.py     # ask() pipeline: plan -> retrieve -> agents -> validate
  api.py         # stdlib REST API
  evaluation.py  # scripted Q&A harness with precision/coverage/faithfulness
tests/           # 36 pytest tests: corpus, retrieval, agents, service, API, eval
run_demo.py      # three demo questions
run_server.py    # start the API
Dockerfile       # python:3.12-slim image
```

## Honest limits

- Retrieval is TF-IDF, not embeddings or a vector database; ranking quality
  is limited (mean precision@3 0.58 on the scripted set) and would improve
  with a real embedding retriever.
- Agents are deterministic policies, not LLM reasoning; prompt engineering,
  tool use and multi-step planning are interface-shaped, not live.
- All figures are synthetic; the budget suggestion is arithmetic on seeded
  data, not a real media plan. Nothing here is production GenAI experience.
