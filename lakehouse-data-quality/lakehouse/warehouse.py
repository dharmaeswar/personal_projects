"""Backend data-engineering warehouse load, in the spirit of Snowflake + Kafka.

A Kafka-style event stream (partition + offset per event) lands in a staging
area the way Snowflake ``COPY INTO`` loads files into a staging table, and a
``MERGE`` then loads a star-schema warehouse: slowly changing dimension
tables (SCD Type 2) and an idempotent fact table. This runs locally with
pandas + Parquet — no Kafka broker or Snowflake account is involved — and
each operation names the warehouse operation it mirrors:

- Kafka poll / commit offsets  -> :func:`consume_events` per batch
- exactly-once via idempotency -> dedup on ``event_id`` against the
                                  consumer's seen ids
- Snowflake COPY INTO staging  -> :func:`stage_events` (Parquet + manifest)
- Snowflake MERGE into dims    -> :func:`load_customer_dim` /
                                  :func:`load_product_dim` (SCD Type 2)
- Snowflake MERGE into fact    -> :func:`load_order_fact` (merge on
                                  ``order_id``; a re-run inserts 0 rows)
- warehouse reconciliation     -> :func:`reconcile_warehouse` (fact revenue
                                  must equal staged valid-event revenue)

All event data is synthetic and seeded. Nothing here is a claim about any
real institution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REGIONS = ["North", "South", "East", "West"]
SEGMENTS = ["Retail", "Wholesale", "Online"]
PRODUCT_PRICES = {
    "P01": 19.99, "P02": 49.50, "P03": 9.95, "P04": 129.00,
    "P05": 24.75, "P06": 89.99, "P07": 14.50, "P08": 199.00,
}
BASE_TIME = datetime(2026, 11, 23, 9, 0, 0, tzinfo=timezone.utc)


def _region_for(customer_id: str) -> str:
    return REGIONS[int(customer_id[1:]) % len(REGIONS)]


def _segment_for(customer_id: str) -> str:
    return SEGMENTS[int(customer_id[1:]) % len(SEGMENTS)]


def generate_warehouse_events(n: int = 150, seed: int = 7) -> pd.DataFrame:
    """Seeded synthetic order events, in Kafka offset order.

    Returns ``n`` base events plus 10 planted rows: 5 replayed events (same
    ``event_id`` with a new offset, as a Kafka redelivery), 3 events naming
    an unknown customer, and 2 events with a negative quantity. Every base
    event has a unique ``order_id``.
    """
    rng = np.random.default_rng(seed)
    customer_ids = [f"C{i:03d}" for i in range(1, 21)]
    product_ids = sorted(PRODUCT_PRICES)
    rows = []
    for i in range(n):
        customer_id = str(rng.choice(customer_ids))
        product_id = str(rng.choice(product_ids))
        quantity = int(rng.integers(1, 6))
        rows.append({
            "event_id": f"EVT-{i + 1:04d}",
            "kafka_partition": int(i % 3),
            "kafka_offset": i,
            "order_id": f"ORD-{i + 1:04d}",
            "customer_id": customer_id,
            "product_id": product_id,
            "quantity": quantity,
            "unit_price": PRODUCT_PRICES[product_id],
            "event_time": BASE_TIME + timedelta(minutes=int(i)),
        })
    # 5 replays: same event_id, fresh offsets (Kafka redelivery).
    for j in range(5):
        replay = dict(rows[j])
        replay["kafka_offset"] = n + j
        rows.append(replay)
    # 3 unknown customers + 2 negative quantities (new event ids).
    for j in range(3):
        rows.append({
            "event_id": f"EVT-BAD-C{j + 1}",
            "kafka_partition": 0,
            "kafka_offset": n + 5 + j,
            "order_id": f"ORD-BAD-C{j + 1}",
            "customer_id": "C999",
            "product_id": "P01",
            "quantity": 2,
            "unit_price": PRODUCT_PRICES["P01"],
            "event_time": BASE_TIME + timedelta(minutes=n + 5 + j),
        })
    for j in range(2):
        rows.append({
            "event_id": f"EVT-BAD-Q{j + 1}",
            "kafka_partition": 1,
            "kafka_offset": n + 8 + j,
            "order_id": f"ORD-BAD-Q{j + 1}",
            "customer_id": "C001",
            "product_id": "P02",
            "quantity": -3,
            "unit_price": PRODUCT_PRICES["P02"],
            "event_time": BASE_TIME + timedelta(minutes=n + 8 + j),
        })
    frame = pd.DataFrame(rows).sort_values("kafka_offset").reset_index(drop=True)
    return frame


@dataclass
class ConsumerState:
    """Kafka-style consumer state: committed offset + seen event ids."""

    committed_offset: int = -1
    seen_event_ids: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "committed_offset": self.committed_offset,
            "seen_event_ids": sorted(self.seen_event_ids),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ConsumerState":
        return cls(
            committed_offset=int(payload.get("committed_offset", -1)),
            seen_event_ids=set(payload.get("seen_event_ids", [])),
        )


def consume_events(
    events: pd.DataFrame,
    state: ConsumerState | None = None,
    batch_size: int = 50,
) -> dict:
    """Poll the stream in batches, committing offsets as each batch lands.

    Events already in ``state.seen_event_ids`` are duplicates (a Kafka
    redelivery) and are dropped, never staged twice. Returns the accepted
    frame, the duplicate frame, batch count, and the updated state.
    """
    state = state or ConsumerState()
    fresh = events[events["kafka_offset"] > state.committed_offset]
    accepted_parts, duplicate_parts = [], []
    batches = 0
    for start in range(0, len(fresh), batch_size):
        batch = fresh.iloc[start:start + batch_size]
        is_dup = batch["event_id"].isin(state.seen_event_ids)
        duplicate_parts.append(batch[is_dup])
        new_rows = batch[~is_dup]
        accepted_parts.append(new_rows)
        state.seen_event_ids.update(new_rows["event_id"].tolist())
        state.committed_offset = int(batch["kafka_offset"].max())
        batches += 1
    accepted = (
        pd.concat(accepted_parts, ignore_index=True)
        if accepted_parts else events.iloc[0:0].copy()
    )
    duplicates = (
        pd.concat(duplicate_parts, ignore_index=True)
        if duplicate_parts else events.iloc[0:0].copy()
    )
    return {
        "accepted": accepted,
        "duplicates": duplicates,
        "batches": batches,
        "state": state,
    }


def validate_events(accepted: pd.DataFrame) -> dict:
    """Quarantine staged-candidate rows that fail warehouse load rules.

    Rules: the customer must be known (C001–C020) and the quantity must be
    positive. Returns the valid frame and the quarantined frame with a
    ``quarantine_reason`` per row.
    """
    known = {f"C{i:03d}" for i in range(1, 21)}
    bad_customer = ~accepted["customer_id"].isin(known)
    bad_qty = accepted["quantity"] <= 0
    quarantined = accepted[bad_customer | bad_qty].copy()
    reasons = []
    for _, row in quarantined.iterrows():
        if row["customer_id"] not in known:
            reasons.append("unknown_customer")
        else:
            reasons.append("non_positive_quantity")
    quarantined["quarantine_reason"] = reasons
    valid = accepted[~(bad_customer | bad_qty)].copy()
    return {"valid": valid, "quarantined": quarantined}


def stage_events(valid: pd.DataFrame, staging_dir: Path) -> dict:
    """Snowflake-style staged load: write the batch as Parquet + a manifest.

    Mirrors ``COPY INTO <staging_table>``: one staged file per load, with a
    manifest recording rows staged and the load time. Returns the staged
    file path and the manifest payload.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    staged_path = staging_dir / "staged_events.parquet"
    valid.to_parquet(staged_path, index=False)
    manifest = {
        "rows_staged": int(len(valid)),
        "source": "kafka-style event stream",
        "loaded_at": datetime.now(timezone.utc).isoformat(),
    }
    (staging_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return {"staged_path": staged_path, "manifest": manifest}


def _scd2_load(
    staged: pd.DataFrame,
    dim_dir: Path,
    key_col: str,
    attr_cols: list[str],
    surrogate_col: str,
) -> dict:
    """Generic SCD Type 2 load: new rows open, changed rows close + reopen.

    A changed attribute closes the current version (``valid_to`` set,
    ``is_current`` cleared) and opens a new version with the next surrogate
    key. Unchanged rows are left alone, so a re-run of the same batch is a
    no-op. Returns counts of inserted, updated (closed + reopened), and
    unchanged rows.
    """
    dim_dir.mkdir(parents=True, exist_ok=True)
    dim_path = dim_dir / "dimension.parquet"
    if dim_path.exists():
        dim = pd.read_parquet(dim_path)
    else:
        dim = pd.DataFrame(columns=[
            surrogate_col, key_col, *attr_cols,
            "valid_from", "valid_to", "is_current",
        ])
    incoming = staged[[key_col, *attr_cols]].drop_duplicates(key_col)
    now = datetime.now(timezone.utc).isoformat()
    inserted = updated = unchanged = 0
    next_key = int(dim[surrogate_col].max()) + 1 if len(dim) else 1
    new_rows = []
    for _, row in incoming.iterrows():
        current = dim[(dim[key_col] == row[key_col]) & (dim["is_current"] == True)]  # noqa: E712
        if len(current) == 0:
            new_rows.append({
                surrogate_col: next_key, key_col: row[key_col],
                **{c: row[c] for c in attr_cols},
                "valid_from": now, "valid_to": None, "is_current": True,
            })
            next_key += 1
            inserted += 1
            continue
        cur = current.iloc[0]
        if all(str(cur[c]) == str(row[c]) for c in attr_cols):
            unchanged += 1
            continue
        dim.loc[current.index, "is_current"] = False
        dim.loc[current.index, "valid_to"] = now
        new_rows.append({
            surrogate_col: next_key, key_col: row[key_col],
            **{c: row[c] for c in attr_cols},
            "valid_from": now, "valid_to": None, "is_current": True,
        })
        next_key += 1
        updated += 1
    if new_rows:
        dim = pd.concat([dim, pd.DataFrame(new_rows)], ignore_index=True)
    dim.to_parquet(dim_path, index=False)
    return {"inserted": inserted, "updated": updated, "unchanged": unchanged,
            "dim_path": dim_path}


def load_customer_dim(staged: pd.DataFrame, dim_dir: Path) -> dict:
    """SCD Type 2 load of the customer dimension (region, segment)."""
    enriched = staged.copy()
    enriched["region"] = enriched["customer_id"].map(_region_for)
    enriched["segment"] = enriched["customer_id"].map(_segment_for)
    return _scd2_load(enriched, dim_dir, "customer_id",
                       ["region", "segment"], "customer_key")


def load_product_dim(staged: pd.DataFrame, dim_dir: Path) -> dict:
    """SCD Type 2 load of the product dimension (unit price)."""
    enriched = staged.copy()
    enriched["unit_price_dim"] = enriched["unit_price"]
    return _scd2_load(enriched, dim_dir, "product_id",
                       ["unit_price_dim"], "product_key")


def load_order_fact(staged: pd.DataFrame, dim_dir: Path, fact_dir: Path) -> dict:
    """Idempotent MERGE of orders into the fact table, on ``order_id``.

    Only orders not already present are inserted, so re-running the same
    batch inserts 0 rows. The customer surrogate key comes from the current
    customer-dimension version. Returns inserted and skipped counts.
    """
    fact_dir.mkdir(parents=True, exist_ok=True)
    fact_path = fact_dir / "fact_orders.parquet"
    dim_path = dim_dir / "dimension.parquet"
    dim = pd.read_parquet(dim_path)
    current_dim = dim[dim["is_current"] == True][["customer_id", "customer_key"]]  # noqa: E712
    merged = staged.merge(current_dim, on="customer_id", how="left")
    merged["total_amount"] = merged["quantity"] * merged["unit_price"]
    fact = merged[[
        "order_id", "customer_key", "product_id", "quantity",
        "unit_price", "total_amount", "event_time",
    ]].copy()
    if fact_path.exists():
        existing = pd.read_parquet(fact_path)
        new_rows = fact[~fact["order_id"].isin(set(existing["order_id"]))]
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        new_rows = fact
        combined = fact
    combined.to_parquet(fact_path, index=False)
    return {"inserted": int(len(new_rows)),
            "skipped": int(len(fact) - len(new_rows)),
            "fact_path": fact_path}


def reconcile_warehouse(staged: pd.DataFrame, fact_dir: Path) -> dict:
    """Reconcile fact revenue back to the staged valid events.

    Fact ``total_amount`` must equal staged ``quantity * unit_price`` within
    0.01; any gap means the MERGE lost or duplicated rows.
    """
    fact = pd.read_parquet(fact_dir / "fact_orders.parquet")
    expected = float((staged["quantity"] * staged["unit_price"]).sum())
    actual = float(fact["total_amount"].sum())
    return {
        "expected_revenue": round(expected, 2),
        "fact_revenue": round(actual, 2),
        "difference": round(actual - expected, 2),
        "reconciled": abs(actual - expected) <= 0.01,
        "fact_rows": int(len(fact)),
    }


def run_warehouse(base_dir: Path) -> dict:
    """Run the full backend load: consume -> validate -> stage -> dims -> fact.

    ``base_dir`` holds the warehouse tables (``staging/``, ``dim_customer/``,
    ``dim_product/``, ``fact_orders/``). Returns a summary dict.
    """
    events = generate_warehouse_events()
    consumed = consume_events(events)
    checked = validate_events(consumed["accepted"])
    staged = stage_events(checked["valid"], base_dir / "staging")
    customer_dim = load_customer_dim(checked["valid"], base_dir / "dim_customer")
    product_dim = load_product_dim(checked["valid"], base_dir / "dim_product")
    fact = load_order_fact(checked["valid"], base_dir / "dim_customer",
                           base_dir / "fact_orders")
    reconciliation = reconcile_warehouse(checked["valid"], base_dir / "fact_orders")
    return {
        "events_received": int(len(events)),
        "duplicates_dropped": int(len(consumed["duplicates"])),
        "batches": consumed["batches"],
        "committed_offset": consumed["state"].committed_offset,
        "quarantined": int(len(checked["quarantined"])),
        "rows_staged": staged["manifest"]["rows_staged"],
        "customer_dim": {k: v for k, v in customer_dim.items() if k != "dim_path"},
        "product_dim": {k: v for k, v in product_dim.items() if k != "dim_path"},
        "fact_inserted": fact["inserted"],
        "fact_skipped": fact["skipped"],
        "reconciliation": reconciliation,
    }
