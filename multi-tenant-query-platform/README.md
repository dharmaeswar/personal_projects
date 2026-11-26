# Multi-Tenant Query Platform

A portfolio project for the **Box — Senior Software Engineer, Query Platform** application (job 8393885, Redwood City, CA). It models the platform layer behind Box's Query Platform idea: many tenants define their own schemas and query their data in real time — the foundation for custom applications, dashboards, real-time analytics, and search/AI experiences.

**All data is synthetic.** No real Box data, customers, or documents are used, and nothing here describes a real Box system. There is no live Kubernetes cluster, BigTable, Elasticsearch, or Spark: the index, store, and query engine are plain Python so the platform logic can be tested end to end.

## Problem statement

When one platform serves many tenants, the platform team has to solve problems no single tenant sees:

- **Tenant-defined schemas** — each tenant defines its own fields and types; schemas are versioned so old documents stay valid when a schema changes.
- **Real-time query** — filters, full-text search, sorting, pagination, and aggregations over the matched set, answered from an inverted index rather than a full scan.
- **Tenant isolation** — one tenant's schemas, documents, and index terms must never leak into another tenant's results.
- **Safe ingest** — streaming ingest retries (Kafka/PubSub at-least-once delivery) must not duplicate documents, so ingest is idempotent on document id.
- **Operability** — per-operation latency and error counters so on-call can see slow queries and ingest failures without digging through logs.

## What is inside

```
query_platform/
  schemas.py    Versioned tenant schemas (FieldDef, SchemaVersion, SchemaRegistry)
  store.py      Document store: idempotent insert/upsert, JSON snapshot round-trip
  index.py      Inverted index for full-text search + exact-match field indexes
  query.py      Query engine: filters ($eq/$ne/$gt/$gte/$lt/$lte/$in), search, sort,
                pagination, aggregations (count, sum, avg, group-by)
  service.py    Tenant-scoped service API + latency/error observability
run_demo.py     End-to-end demo: two tenants, schemas, ingest, queries, aggregations
tests/          Pytest suite covering every module
```

## Run it

```bash
python3 run_demo.py
python3 -m pytest -q
```

## Example

```python
from query_platform import FieldDef, QueryPlatformService

svc = QueryPlatformService()
svc.define_schema("acme", "contracts", [
    FieldDef("title", "string", required=True),
    FieldDef("status", "string", required=True),
    FieldDef("amount", "number", required=True),
])
svc.ingest("acme", "contracts", "c1",
           {"title": "Master services agreement renewal",
            "status": "approved", "amount": 120000})
svc.query("acme", "contracts", {
    "search": "renewal",
    "filter": {"status": "approved", "amount": {"$gte": 50000}},
    "sort": [("amount", "desc")],
    "aggregate": {"count": True, "sum": {"total_amount": "amount"}},
})
```

## Honest limits

- In-memory store and index (JSON snapshot only); no BigTable/Elasticsearch/Spark, no Kubernetes, no Istio — the deployment and scaling layers the real role operates are modeled as module boundaries, not run here.
- Single-process, single-node: no sharding, replication, or distributed consistency; the "distributed systems" work is the idempotent-ingest and versioning design, not a cluster.
- Search is token AND over lowercased alphanumeric terms; no ranking, stemming, or fuzzy matching.
- Demonstrated on a handful of seeded documents, not at production scale.
