# Pharmacy Claims 340B ETL

A portfolio project for the **CVS Health — Data Engineer (Wellpartner, Req R1108581)** application. It builds the ETL the posting describes: pharmacy claims, 340B third-party administrator (TPA) captures, covered-entity eligibility files, and drug inventory/pricing feeds are ingested from CSV, XML, flat-file, and JSON sources, validated against 340B program rules, and loaded into a SQL Server-style data warehouse — with incremental and full loads on daily, weekly, and monthly cycles, and reconciliation of every load.

**All data is synthetic and seeded.** No real patient, pharmacy, claim, or 340B program data is used. Nothing here describes a real CVS Health system. The warehouse runs locally on SQLite as a stand-in for SQL Server; the production T-SQL scripts in `claims_etl/sql/` target SQL Server and are validated structurally (see below).

## Problem statement

Wellpartner has to prove every 340B claim is eligible before it is paid: the patient must be covered-entity eligible on the fill date, the drug and quantity must match the pricing feed, and the TPA must have captured the claim. The source feeds disagree — eligibility files are fixed-width, TPA captures arrive as XML, claims arrive as CSV, pricing as JSON — and a bad row loaded into the warehouse becomes a compliance finding. This project fixes that with a validated pipeline:

- **Ingest** (`claims_etl/ingest.py`) — one parser per source format (CSV claims, XML TPA captures, fixed-width eligibility, JSON drug pricing), each normalising to typed records and reporting malformed rows instead of crashing.
- **Validate** (`claims_etl/validate.py`) — six 340B rules: patient eligibility on the fill date, 11-digit NDC format, quantity / days-supply bounds, amount equals quantity × unit price, no duplicate claim IDs, and a matching TPA capture. Every failure is quarantined with the rule that caught it; nothing invalid reaches the warehouse.
- **Load** (`claims_etl/warehouse.py`, `claims_etl/loads.py`) — staging → fact load with a watermark for incremental loads and a full-refresh mode; every load writes a load-log row and a reconciliation report (source rows vs loaded vs quarantined).
- **T-SQL** (`claims_etl/sql/`) — the production scripts: warehouse tables, `usp_LoadClaims`, `usp_Validate340B`, and `usp_ReconcileLoads` stored procedures. They are SQL Server T-SQL and are checked structurally by the test suite; the runnable pipeline mirrors their logic on SQLite so the behaviour is testable without a SQL Server instance.

## Layout

```
claims_etl/
  ingest.py      CSV / XML / flat-file / JSON parsers
  validate.py    340B validation rules + quarantine
  warehouse.py   warehouse schema, incremental + full loads
  loads.py       orchestration: ingest -> validate -> load -> reconcile
  sql/           T-SQL scripts for SQL Server
    01_create_tables.sql
    02_sp_load_claims.sql
    03_sp_validate_340b.sql
    04_sp_reconcile.sql
data/
  pharmacy_claims.csv   12 seeded claims (5 valid, 7 quarantined)
  claims_batch2.csv     2 later claims for the incremental-load demo
  tpa_340b.xml          TPA captures
  eligibility.txt       fixed-width covered-entity eligibility
  drug_pricing.json     NDC -> unit price
run_demo.py             end-to-end demo: full load, then incremental load
tests/                  pytest suite (ingest, rules, warehouse, loads, T-SQL)
```

## Demo

```
python run_demo.py
```

Full load: 12 source claims → 5 loaded, 7 quarantined (ineligible patient, expired eligibility window, duplicate claim, malformed NDC, zero quantity, amount mismatch, days-supply over the 90-day limit, missing TPA capture). Incremental load: 2 new claims dated after the watermark → 2 loaded; re-running the same batch loads 0.

## What it deliberately does not claim

- SSIS is **not** implemented here: the pipeline is Python, and the README says so. Dharma's ETL, SQL, stored-procedure, and data-validation experience is in the resume; SSIS itself is flagged as a gap in the application notes.
- No real 340B, patient, or pharmacy data; no SQL Server instance is required or contacted.
