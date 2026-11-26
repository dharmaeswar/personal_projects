# Investment Research AI Assistant

Role project for T. Rowe Price — Investment AI Solutions Analyst, Req 81557 (Baltimore, MD).
An analyst/PM research copilot: retrieval-augmented Q&A over investment research notes
(earnings-call style notes, filing excerpts, analyst notes), with grounded answers that cite
their sources, retrieval evaluation, compliance guardrails, and observability logging.
Extended Nov 26, 2026 for Balyasny Asset Management — Data Analyst, L/S Equities (REQ8771, New York):
a single-stock KPI inflection module for the PM team's workflow — monitor company KPIs and an
alternative-data proxy, flag inflections, forecast the next quarter, and backtest the long/short signal.

All documents are **synthetic, seeded, fictional** research notes written for this demo.
No real company data, no T. Rowe Price affiliation, no live LLM call: the answer
composer is a deterministic extractive stand-in that only repeats what the retrieved
passages say, so groundedness can be measured exactly.

## What it is

- `research_assistant/corpus.py` — seeded corpus of 12 fictional research documents
  (earnings notes, 10-K style excerpts, analyst notes, risk memos) with source metadata.
- `research_assistant/chunking.py` — splits documents into passages (max ~120 words,
  sentence-aware, keeps source + section metadata on every chunk).
- `research_assistant/retrieval.py` — TF-IDF-weighted keyword retrieval over chunks
  (stdlib only, deterministic). Returns ranked passages with scores.
- `research_assistant/qa.py` — grounded Q&A: retrieves top-k passages, composes an
  answer only from retrieved text, attaches a citation to every claim, and says
  "not covered by the research notes" instead of inventing an answer when nothing
  retrieved is relevant.
- `research_assistant/guardrails.py` — compliance checks on every answer: no claim
  without a citation, no forward-looking guarantee language, no material-non-public
  information markers, no recommendation to buy/sell a specific security.
- `research_assistant/evaluate.py` — retrieval + groundedness evaluation over a seeded
  Q&A set: recall@k, groundedness rate, hallucination-flag rate, guardrail pass rate.
- `research_assistant/observability.py` — JSONL run log of every query (question,
  retrieved doc ids, scores, guardrail verdict, latency).
- `run_research_demo.py` — runner: answers three sample analyst questions, prints the
  answers with citations, runs the evaluation, writes `research_eval_report.json`.

## Single-stock KPI inflection analysis (new, Nov 2026 — built for a Balyasny L/S Equities Data Analyst role)

- `research_assistant/kpi.py` — the quantitative half of a PM team's workflow, on a seeded
  4-company x 12-quarter panel (2024-Q1 to 2026-Q4) of fictional companies from the same
  corpus: revenue growth (YoY %), operating margin (%), an alternative-data proxy index
  (base 100), and next-quarter stock returns.
  - `load_kpi_panel` — deterministic seeded panel. Two planted level shifts are the
    detector's ground truth: Helix Software Group revenue growth steps up from 2025-Q3,
    Northwind Energy Partners operating margin steps down from 2026-Q1.
  - `detect_inflections` — trailing 4-quarter mean/std z-score breaks (|z| >= 2); flags the
    quarter, value, z-score and direction. Both planted breaks are found (Helix 2025-Q3
    z=29.71; Northwind 2026-Q1 z=-57.66). The detector also flags ordinary noise moves, so a
    flag alone is never a position — the signal requires inflection + trend + alt data together.
  - `forecast_kpi` — OLS regression on the time index: next-quarter forecast, slope and R².
  - `kpi_signal` — per-name score from -3 to +3: latest-quarter inflection direction, sign
    of the revenue-growth forecast slope, sign of the 4-quarter alt-data momentum (beyond
    ±5%). Capped at a formation quarter, so a backtest signal never sees later data.
  - `backtest_kpi_signal` — quarterly long/short: long the top-scored name, short the
    bottom-scored name, hold one quarter, 5 bps charged on two-way turnover. No look-ahead:
    the signal at quarter t uses KPI data through t only.
  - `dashboard_summary` / `kpi_report` — one row per name (latest KPIs, inflections,
    forecast, signal, LONG/SHORT/NEUTRAL) plus the backtest.
- `run_kpi_demo.py` — prints the dashboard and backtest, writes `kpi_report.json`.
- `tests/test_kpi.py` — 14 tests: panel shape and determinism, both planted breaks, quiet
  detector on flat series, forecast slope recovery, no-look-ahead (corrupting future data
  leaves the signal at the formation quarter unchanged), backtest metrics, dashboard
  completeness, end-to-end report.

## Measured results (seeded panel, `kpi_report.json`)

- Dashboard: Helix Software Group LONG (score 2 — revenue growth 19.51% YoY, alt-data
  momentum +9.82% over 4 quarters, next-quarter forecast 22.92% growth, R² 0.766);
  Acme, Beacon and Northwind NEUTRAL (score 1 each).
- Backtest (7 quarterly trades): hit rate 0.286, mean quarterly return +0.74%,
  total return +5.19%.

## How to run

```bash
python -m pytest -q
python run_research_demo.py
python run_kpi_demo.py
```

## Honest limits

- Synthetic seeded corpus only; no real filings, earnings calls, or market data.
- The answer composer is extractive and deterministic, not a deployed LLM agent;
  no LangChain / LangGraph / AutoGen integration is claimed.
- Retrieval is TF-IDF keyword matching, not embeddings; it is a working baseline
  with measured recall, not a production search system.
- Guardrails are rule-based checks, not a compliance review; they demonstrate the
  control pattern, not legal sign-off.
