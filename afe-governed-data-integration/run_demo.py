"""End-to-end demo: two legacy client feeds + a reference API, run through
the pod pipeline into a governed SQLite warehouse, with lineage, a
retrieval index, and a feature-store snapshot.

All data is synthetic and seeded. Nothing here is real client, tax, or
financial data.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from afe_data.contracts import DataContract
from afe_data.pipeline import PodPipeline
from afe_data.sources import (
    OracleExtractAdapter,
    PostgresDumpAdapter,
    RestApiAdapter,
    SourceProfile,
)

BASE = Path(__file__).parent
DB = BASE / "afe_demo.db"

POSTGRES_V2 = """position_id,client_id,instrument,notional,currency,valuation_date,tax_id
P-1001,ACME,IRS-SWAP-5Y,2500000,USD,2026-11-20,***-11-1001
P-1002,ACME,CDS-IG-3Y,1200000,USD,2026-11-20,***-11-1002
P-1003,GLOBEX,FX-FWD-EURUSD,-750000,EUR,2026-11-20,***-11-1003
P-1004,ACME,IRS-SWAP-10Y,,USD,2026-11-20,***-11-1004
P-1002,ACME,CDS-IG-3Y,1200000,USD,2026-11-20,***-11-1002
"""

ORACLE_EXTRACT = """RISK_ID|CLIENT|INSTRUMENT|NOTIONAL|CCY|VAL_DT
R-2001|ACME|IRS-SWAP-5Y|2500000|USD|2026-11-20
R-2002|GLOBEX|FX-FWD-EURUSD|-750000|EUR|2026-11-20
R-2003|INITECH|BOND-UST-10Y|5000000|USD|2026-11-20
"""

API_PAGES = [
    [{"client_id": "ACME", "legal_name": "Acme Holdings LLC", "jurisdiction": "US-DE"},
     {"client_id": "GLOBEX", "legal_name": "Globex Corp", "jurisdiction": "US-NY"}],
    [{"client_id": "INITECH", "legal_name": "Initech Inc", "jurisdiction": "US-TX"}],
]


def main() -> dict:
    if DB.exists():
        DB.unlink()
    pipe = PodPipeline(DB)

    pg_contract = DataContract(
        dataset="client-positions",
        expected_columns=["position_id", "client_id", "instrument", "notional",
                          "currency", "valuation_date", "tax_id"],
        required_columns=["position_id", "client_id", "instrument", "notional"],
        freshness_hours=24,
        completeness_floor=0.6,
    )
    pg = PostgresDumpAdapter(
        SourceProfile("client-postgres", "Postgres", "on-prem", "client tax ops"),
        POSTGRES_V2, "v2",
    )
    reference_ids = {"ACME", "GLOBEX", "INITECH"}
    result_pg = pipe.run(pg, pg_contract, reference_ids,
                         previous_schema=["position_id", "client_id", "instrument",
                                          "notional", "currency", "valuation_date"])
    # The recorded schema is already v2; the only drift is the newly added
    # tax_id column (additive evolution, non-blocking). The v1 -> v2 rename
    # (pos_id -> position_id) is handled by the transform field map.

    oracle_contract = DataContract(
        dataset="risk-positions",
        expected_columns=["RISK_ID", "CLIENT", "INSTRUMENT", "NOTIONAL", "CCY", "VAL_DT"],
        required_columns=["RISK_ID", "CLIENT", "INSTRUMENT", "NOTIONAL"],
        freshness_hours=24,
        completeness_floor=0.8,
    )
    oracle = OracleExtractAdapter(
        SourceProfile("risk-oracle", "Oracle", "on-prem", "client risk"),
        ORACLE_EXTRACT, "v1",
    )
    result_oracle = pipe.run(oracle, oracle_contract, reference_ids,
                             previous_schema=["RISK_ID", "CLIENT", "INSTRUMENT",
                                              "NOTIONAL", "CCY", "VAL_DT"])

    api = RestApiAdapter(
        SourceProfile("client-reference-api", "REST API", "cloud", "client master data"),
        API_PAGES, fail_page=1,
    )
    api_rows = api.read()

    with sqlite3.connect(DB) as conn:
        positions = conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]
        quarantined = conn.execute("SELECT record_id, reason FROM quarantine").fetchall()

    hits = pipe.index.search("IRS swap position ACME", top_k=2)
    features = pipe.feature_store_snapshot()
    summary = {
        "postgres": result_pg,
        "oracle": result_oracle,
        "api_rows": len(api_rows),
        "api_retries": api.retries_used,
        "positions_loaded": positions,
        "quarantined": [list(q) for q in quarantined],
        "retrieval_top_hit": hits[0].doc_id if hits else None,
        "retrieval_top_score": round(hits[0].score, 3) if hits else None,
        "feature_rows": len(features),
        "lineage_entries": len(pipe.lineage.entries),
    }
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    main()
