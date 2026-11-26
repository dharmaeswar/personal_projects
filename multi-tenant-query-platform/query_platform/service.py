"""Query platform service: the tenant-facing API over registry, store, index.

One service instance serves many tenants. Every operation is scoped to a
tenant, so a query for tenant A can never see tenant B's schemas, documents
or index terms. The service records per-operation latency and counts so the
team can watch reliability and operability (the on-call half of the job):
slow-query and error-rate signals come from these counters, not from logs.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict

from .index import InvertedIndex
from .query import QueryEngine
from .schemas import FieldDef, SchemaRegistry
from .store import DocumentStore


class QueryPlatformService:
    def __init__(self):
        self.registry = SchemaRegistry()
        self.store = DocumentStore()
        self.index = InvertedIndex()
        self.engine = QueryEngine(self.store, self.index)
        self._op_counts: Counter = Counter()
        self._op_errors: Counter = Counter()
        self._latency_ms: dict[str, list[float]] = defaultdict(list)

    # -- observability -------------------------------------------------
    def _timed(self, op: str, fn, *args, **kwargs):
        start = time.perf_counter()
        try:
            result = fn(*args, **kwargs)
            self._op_counts[op] += 1
            return result
        except Exception:
            self._op_errors[op] += 1
            raise
        finally:
            self._latency_ms[op].append((time.perf_counter() - start) * 1000)

    def stats(self) -> dict:
        return {
            "operations": dict(self._op_counts),
            "errors": dict(self._op_errors),
            "avg_latency_ms": {
                op: round(sum(v) / len(v), 3) for op, v in self._latency_ms.items() if v
            },
        }

    # -- schema --------------------------------------------------------
    def define_schema(self, tenant: str, collection: str, fields: list[FieldDef]):
        return self._timed("define_schema", self.registry.register, tenant, collection, fields)

    # -- ingest --------------------------------------------------------
    def ingest(self, tenant: str, collection: str, doc_id: str, fields: dict,
               upsert: bool = False) -> dict:
        def _ingest():
            schema = self.registry.latest(tenant, collection)
            if schema is None:
                raise ValueError(f"no schema defined for {tenant}/{collection}")
            errors = schema.validate(fields)
            if errors:
                raise ValueError("schema validation failed: " + "; ".join(errors))
            doc, created = self.store.insert(
                tenant, collection, doc_id, schema.version, fields, upsert=upsert)
            indexed = {f.name for f in schema.fields if f.indexed}
            self.index.index_document(tenant, collection, doc_id, fields, indexed)
            return {"doc_id": doc_id, "created": created,
                    "schema_version": schema.version, "seq": doc.seq}
        return self._timed("ingest", _ingest)

    # -- query ---------------------------------------------------------
    def query(self, tenant: str, collection: str, query: dict) -> dict:
        def _query():
            if self.registry.latest(tenant, collection) is None:
                raise ValueError(f"no schema defined for {tenant}/{collection}")
            return self.engine.execute(tenant, collection, query)
        return self._timed("query", _query)

    def health(self) -> dict:
        return {
            "status": "ok",
            "tenants": sorted({t for (t, _) in self.registry._schemas}),
            "documents": len(self.store._docs),
            "errors": dict(self._op_errors),
        }
