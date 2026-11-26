"""End-to-end demo: two tenants define schemas, ingest, and query in real time.

Tenant "acme" tracks contracts; tenant "globex" tracks support tickets.
The demo shows tenant isolation, schema validation, idempotent re-ingest,
full-text search, filtered queries, and aggregations.
"""

from query_platform import FieldDef, QueryPlatformService


def main():
    svc = QueryPlatformService()

    svc.define_schema("acme", "contracts", [
        FieldDef("title", "string", required=True),
        FieldDef("status", "string", required=True),
        FieldDef("amount", "number", required=True),
        FieldDef("owner", "string"),
        FieldDef("tags", "string_list"),
    ])
    svc.define_schema("globex", "tickets", [
        FieldDef("subject", "string", required=True),
        FieldDef("priority", "string", required=True),
        FieldDef("hours_open", "number", required=True),
    ])

    docs = [
        ("acme", "contracts", "c1", {"title": "Master services agreement renewal",
                                      "status": "approved", "amount": 120000,
                                      "owner": "legal", "tags": ["renewal", "q4"]}),
        ("acme", "contracts", "c2", {"title": "Vendor agreement for cloud hosting",
                                      "status": "draft", "amount": 45000,
                                      "owner": "ops", "tags": ["vendor"]}),
        ("acme", "contracts", "c3", {"title": "Renewal addendum for data processing",
                                      "status": "approved", "amount": 80000,
                                      "owner": "legal", "tags": ["renewal"]}),
        ("globex", "tickets", "t1", {"subject": "Dashboard loads slowly at peak",
                                      "priority": "high", "hours_open": 26}),
        ("globex", "tickets", "t2", {"subject": "Export button missing on report page",
                                      "priority": "low", "hours_open": 5}),
    ]
    for tenant, coll, doc_id, fields in docs:
        print(svc.ingest(tenant, coll, doc_id, fields))

    # Idempotent retry of the same document: no duplicate.
    print("retry c1:", svc.ingest("acme", "contracts", "c1", docs[0][3]))

    print("\n-- full-text search 'renewal' in acme/contracts --")
    print(svc.query("acme", "contracts", {"search": "renewal"}))
    print("\n-- approved contracts over 50000, sorted by amount desc, with totals --")
    print(svc.query("acme", "contracts", {
        "filter": {"status": "approved", "amount": {"$gte": 50000}},
        "sort": [("amount", "desc")],
        "aggregate": {"count": True, "sum": {"total_amount": "amount"},
                      "avg": {"avg_amount": "amount"},
                      "group_by": {"by_status": "status"}},
    }))
    print("\n-- globex cannot see acme documents --")
    print(svc.query("globex", "tickets", {"search": "renewal"}))
    print("\n-- service stats --")
    print(svc.stats())
    print("\n-- health --")
    print(svc.health())


if __name__ == "__main__":
    main()
