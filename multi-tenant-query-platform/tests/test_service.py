import pytest

from query_platform import FieldDef, QueryPlatformService


def _svc():
    svc = QueryPlatformService()
    svc.define_schema("acme", "contracts", [
        FieldDef("title", "string", required=True),
        FieldDef("status", "string", required=True),
        FieldDef("amount", "number", required=True),
    ])
    return svc


def test_end_to_end_ingest_search_aggregate():
    svc = _svc()
    svc.ingest("acme", "contracts", "c1", {"title": "renewal agreement", "status": "approved", "amount": 10})
    svc.ingest("acme", "contracts", "c2", {"title": "vendor agreement", "status": "draft", "amount": 5})
    r = svc.query("acme", "contracts", {"search": "agreement", "aggregate": {"count": True}})
    assert r["total"] == 2 and r["aggregations"]["count"] == 2
    r = svc.query("acme", "contracts", {"filter": {"status": "approved"}})
    assert r["total"] == 1


def test_invalid_doc_rejected_and_counted_as_error():
    svc = _svc()
    with pytest.raises(ValueError):
        svc.ingest("acme", "contracts", "c1", {"title": "no status", "amount": 1})
    assert svc.stats()["errors"].get("ingest", 0) == 1
    assert svc.store.count("acme", "contracts") == 0


def test_unknown_collection_rejected():
    svc = QueryPlatformService()
    with pytest.raises(ValueError):
        svc.ingest("acme", "contracts", "c1", {"title": "x"})
    with pytest.raises(ValueError):
        svc.query("acme", "contracts", {})


def test_tenant_isolation_end_to_end():
    svc = _svc()
    svc.define_schema("other", "contracts", [FieldDef("title", "string", required=True)])
    svc.ingest("acme", "contracts", "c1", {"title": "secret deal", "status": "approved", "amount": 1})
    svc.ingest("other", "contracts", "c1", {"title": "other deal"})
    r = svc.query("other", "contracts", {"search": "secret"})
    assert r["total"] == 0
    assert svc.query("acme", "contracts", {})["total"] == 1


def test_schema_versioning_old_docs_still_queryable():
    svc = _svc()
    svc.ingest("acme", "contracts", "c1", {"title": "old", "status": "approved", "amount": 1})
    svc.define_schema("acme", "contracts", [
        FieldDef("title", "string", required=True),
        FieldDef("status", "string", required=True),
        FieldDef("amount", "number", required=True),
        FieldDef("owner", "string"),
    ])
    svc.ingest("acme", "contracts", "c2",
               {"title": "new", "status": "draft", "amount": 2, "owner": "ops"})
    assert svc.query("acme", "contracts", {})["total"] == 2
    assert svc.store.get("acme", "contracts", "c1").schema_version == 1
    assert svc.store.get("acme", "contracts", "c2").schema_version == 2


def test_health_and_stats():
    svc = _svc()
    svc.ingest("acme", "contracts", "c1", {"title": "x", "status": "approved", "amount": 1})
    svc.query("acme", "contracts", {})
    assert svc.health()["status"] == "ok"
    assert svc.health()["documents"] == 1
    assert svc.stats()["operations"]["ingest"] == 1
    assert svc.stats()["operations"]["query"] == 1
