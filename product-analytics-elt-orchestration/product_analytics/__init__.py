"""Product Analytics ELT Orchestration.

Builds trusted, self-service product analytics from raw product events:
instrumentation contracts, staged ELT, partitioned analytics tables,
window-function metrics (sessions, retention, funnels) defined as code,
a small DAG orchestrator, data-quality checks, a dataset catalog, and a
query-optimization comparison. Runs locally on SQLite (standard library
only); pytest for tests. All data is synthetic and seeded.
"""
