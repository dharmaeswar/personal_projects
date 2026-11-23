"""Run the backend warehouse load and write warehouse_report.txt.

Usage:  python run_warehouse.py
Tables land in lakehouse_tables/warehouse/ (staging, dim_customer,
dim_product, fact_orders). Re-running is safe: the consumer dedups on
event_id, the SCD Type 2 loads leave unchanged rows alone, and the fact
MERGE inserts 0 rows for orders already present.
"""

from __future__ import annotations

from pathlib import Path

from lakehouse.warehouse import run_warehouse

BASE = Path(__file__).parent
WAREHOUSE_DIR = BASE / "lakehouse_tables" / "warehouse"


def main() -> None:
    summary = run_warehouse(WAREHOUSE_DIR)
    rec = summary["reconciliation"]
    lines = [
        "Backend warehouse load (Kafka-style ingest -> Snowflake-style staged MERGE)",
        f"Events received: {summary['events_received']}",
        f"Duplicates dropped (Kafka redelivery): {summary['duplicates_dropped']}",
        f"Micro-batches polled: {summary['batches']}",
        f"Committed offset: {summary['committed_offset']}",
        f"Quarantined (unknown customer / non-positive quantity): {summary['quarantined']}",
        f"Rows staged: {summary['rows_staged']}",
        "Customer dim (SCD Type 2): "
        f"{summary['customer_dim']['inserted']} inserted, "
        f"{summary['customer_dim']['updated']} updated, "
        f"{summary['customer_dim']['unchanged']} unchanged",
        "Product dim (SCD Type 2): "
        f"{summary['product_dim']['inserted']} inserted, "
        f"{summary['product_dim']['updated']} updated, "
        f"{summary['product_dim']['unchanged']} unchanged",
        f"Fact orders inserted: {summary['fact_inserted']} "
        f"({summary['fact_skipped']} skipped as already present)",
        f"Reconciliation: staged revenue {rec['expected_revenue']:.2f} vs "
        f"fact revenue {rec['fact_revenue']:.2f} "
        f"(difference {rec['difference']:.2f}) over {rec['fact_rows']} fact rows",
        f"Reconciled: {'YES' if rec['reconciled'] else 'NO'}",
    ]
    (BASE / "warehouse_report.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
