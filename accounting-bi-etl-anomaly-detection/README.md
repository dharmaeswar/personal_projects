# Accounting BI ETL & Anomaly Detection

A portfolio project for a Senior Data Engineer, Accounting role (Amazon
Accounting BI style). It builds the pipeline an accounting team needs
before close: journal entries arrive as raw feeds from subledgers, and
the pipeline turns them into a close-ready trial balance — validating
every line, checking that each journal balances, catching duplicate
postings, and flagging anomalies for a human to review before the books
close.

**All data is synthetic and seeded.** No real company, journal, or
financial data is used, and nothing here is a claim about any real
institution.

## Problem statement

Accounting BI supports the global Accounting organization with process
automation, automated reporting, and timely, accurate financial data.
Raw journal feeds cannot be trusted directly: a journal can arrive
unbalanced, a posting can be duplicated, an amount can be a typo away
from the truth, and a late entry can land in a period that already
closed. This project catches all of that before the trial balance is
built, and reports what it found instead of failing silently.

## What it does

- **Ingest + validate** — each journal line must satisfy a data
  contract (required fields, one side only, non-negative amounts, known
  chart-of-accounts code, USD, posting date inside its fiscal period).
  Invalid lines go to a quarantine table with the reason, never dropped
  silently.
- **Balance check** — every journal's debits must equal its credits
  (within $0.01). Unbalanced journals are flagged and excluded from the
  trial balance.
- **Deduplication** — a re-posted journal (same content, new entry id)
  is detected; only the first copy reaches the trial balance.
- **Anomaly detection** (auditable rules, no black box):
  - per-account amount outliers via median / MAD modified z-score,
  - round-dollar postings ($5,000+ in whole thousands),
  - weekend postings,
  - postings into already-closed fiscal periods,
  - Benford's-law first-digit check over all amounts.
- **Gold outputs** — `trial_balance.csv` (by account, debits = credits),
  `anomaly_report.json` (every flagged line with its reason), and
  `close_report.json` (counts, unbalanced journals, duplicates, Benford
  deviation). Re-running rebuilds the ledger from the feed, so a re-run
  never double-counts.

## Results on the sample feed

48 journal lines in, 2 quarantined (unknown account; debit and credit
both set), 3 unbalanced journals excluded, 2 duplicate lines excluded,
40 clean lines in the trial balance. Books balance at $459,049.81.
8 lines flagged for review: a $250,000 salaries outlier, a $50,000
round-dollar entry, a Saturday posting, and a posting into closed
period 2026-08 (two lines each). Benford max deviation 0.0831.

## Run it

```bash
python3 -m pytest tests/ -q        # 24 tests
python3 src/run.py                  # reads data/sample_journals.json, writes output/
python3 src/run.py <feed.json> <outdir>   # your own feed
```

Standard library only (SQLite); `requirements.txt` lists pytest.
Regenerate the sample feed with `python3 data/generate_sample_data.py`
(seeded — same output every time).

## Layout

```
src/contracts.py   data contracts + chart of accounts + closed periods
src/ledger.py      SQLite staging, quarantine, balance checks, trial balance
src/anomaly.py     outlier / round-dollar / weekend / late / Benford checks
src/run.py         pipeline runner: ingest -> validate -> balance -> detect -> report
data/              sample_journals.json (synthetic, seeded) + generator
tests/             24 pytest tests (contracts, ledger, anomaly, end-to-end)
output/            ledger.db, trial_balance.csv, anomaly_report.json, close_report.json
```

## How it maps to the role

| Job requirement | Where it lives here |
|---|---|
| ETL pipelines (AWS-style) | `src/run.py` ingest -> validate -> stage -> gold |
| Data modeling / warehousing | staged `raw_lines` + quarantine + flags tables, trial balance as gold |
| SQL | trial balance and balance checks are real SQL over SQLite |
| Anomaly detection / data quality | `src/anomaly.py`, quarantine + journal balance checks |
| Automated reporting | `trial_balance.csv`, `close_report.json`, `anomaly_report.json` |
| Python | the whole pipeline; pandas-free stdlib so it runs anywhere |
