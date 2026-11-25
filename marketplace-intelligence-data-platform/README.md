# Marketplace Intelligence Data Platform
#
# A portfolio project for a Software Engineer II, Data Engineering role
# (Uber Global Intelligence / Data Platform style). It builds the data
# foundation a competitive-intelligence team needs: heterogeneous EXTERNAL
# sources (competitor pricing feeds, demand-signal APIs) plus INTERNAL
# aggregates, integrated into durable, contracted, quality-checked models
# that analysts and ML systems can trust.
#
# All data is synthetic and seeded. No real company, competitor, trip, or
# pricing data is used, and nothing here is a claim about any real company.
#
# ## Problem statement
#
# Marketplace teams need trusted answers — how competitor prices move by
# zone and day, where demand is surging, which zones are underserved — but
# the data arrives from sources that disagree: an external pricing feed
# that renames columns between versions, a demand-signal API that pages
# and fails transiently, and internal aggregates in yet another shape.
# Raw rows land with missing keys, duplicated deliveries, late arrivals,
# and prices that make no sense. Ad-hoc queries against the raw feeds are
# slow and disagree with each other.
#
# This project fixes that with a contracted, quality-checked pipeline:
#
# - **External-source integration** — CSV feeds and a paginated JSON API
#   are ingested through one adapter interface, with schema versions
#   tracked per source and per batch, so an evolving feed never silently
#   changes what lands downstream.
# - **AI-assisted schema mapping** — a mapper proposes field mappings
#   with a confidence score (exact match, known synonym, normalised
#   fuzzy match). Structured-output validation then checks every mapped
#   record against the target schema (required fields, types, enums);
#   low-confidence fields go to a human-review queue instead of being
#   guessed into the warehouse. The mapper is deterministic and
#   rule-based here; in production the same interface fronts an LLM
#   call, and the confidence + validation + review gates are the
#   safeguards that make the LLM output safe to load.
# - **Data contracts** — every dataset has a contract (schema, freshness
#   SLA, completeness floor, allowed evolution). Breaking schema changes
#   are rejected before load; additive changes are accepted and logged.
# - **Incremental ETL with orchestration** — a small DAG runner
#   (validate -> map -> contract -> quality -> load -> reconcile ->
#   publish) with topological ordering, one retry per failed task, and
#   run state recorded so a failed run resumes instead of restarting.
#   Loads are incremental on an event-date watermark and idempotent on
#   the natural key, so re-running a batch or backfilling a date range
#   never double-counts.
# - **Durable data models** — a zone dimension with SCD Type 2 history,
#   a competitor dimension, and a fact table grained at
#   zone + snapshot date + source + competitor, with declared keys and
#   relationships.
# - **Data quality + observability** — missing, duplicated, delayed and
#   inconsistent rows are quarantined with a reason, never silently
#   loaded; source-to-warehouse reconciliation checks row counts and
#   price totals; a run report records every check.
#
# ## Layout
#
# ```
# marketintel/
#   sources.py         external CSV / JSON-API / internal adapters
#   schema_mapping.py  AI-assisted mapping, confidence, review queue
#   contracts.py       data contracts, schema-evolution checks
#   quality.py         validation, quarantine, reconciliation
#   warehouse.py       SQLite models, incremental load, backfill
#   pipeline.py        DAG orchestration, run state, recovery
#   catalog.py         dataset catalog generation
# run_pipeline.py      CLI entry point (writes market_report.json, CATALOG.md)
# data/                synthetic seeded feeds
# tests/               pytest suites
# ```
#
# ## Run it
#
# ```bash
# python -m pytest -q
# python run_pipeline.py
# ```
#
# ## Honest limits
#
# - The "AI" mapper is deterministic and rule-based, not a live LLM call:
#   it demonstrates the mapping interface, confidence scoring,
#   structured-output validation and human-review gate that would wrap a
#   real LLM in production. No LLM is called and no API key is needed.
# - The JSON API source is simulated in-process (paged dicts with an
#   injected transient failure), not a real HTTP service; the retry and
#   pagination logic is the part being demonstrated.
# - The warehouse is SQLite, not Spark/Databricks; the grain, keys,
#   incremental-load and reconciliation patterns are the same ones a
#   Spark job would use, and the PySpark equivalents are named in the
#   module docstrings.
# - Demonstrated on tens of synthetic rows, not at production scale.
