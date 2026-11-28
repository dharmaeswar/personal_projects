"""End-to-end demo for the distributor ETL: full load, then incremental.

Full load: 12 source shipments -> 6 loaded, 6 quarantined (duplicate
shipment, zero quantity, unknown product, amount mismatch, inactive
customer, ship date outside the reporting window). Incremental load:
2 new shipments dated after the watermark -> 2 loaded; re-running the
same batch loads 0.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from distributor_etl import loads, warehouse

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                  "distributor_warehouse.db")


def _show(tag, report):
    print("%s: source=%d loaded=%d quarantined=%d skipped=%d watermark=%s"
          " reconcile=%s"
          % (tag, report["source_rows"], report["loaded_rows"],
             report["quarantined_rows"], report.get("skipped_rows", 0),
             report["watermark"], loads.reconcile(report)))
    for q in report["quarantined"]:
        print("  quarantined %s: %s"
              % (q["shipment_id"], "; ".join(q["violations"])))


def main():
    if os.path.exists(DB):
        os.remove(DB)
    _show("full", loads.run_load(
        DB, os.path.join(DATA, "distributor_shipments.csv"),
        os.path.join(DATA, "distributor_inventory.json"),
        os.path.join(DATA, "distributor_customers.csv"), mode="full"))
    _show("incremental", loads.run_load(
        DB, os.path.join(DATA, "distributor_shipments_batch2.csv"),
        os.path.join(DATA, "distributor_inventory.json"),
        os.path.join(DATA, "distributor_customers.csv"),
        mode="incremental"))
    _show("incremental rerun", loads.run_load(
        DB, os.path.join(DATA, "distributor_shipments_batch2.csv"),
        os.path.join(DATA, "distributor_inventory.json"),
        os.path.join(DATA, "distributor_customers.csv"),
        mode="incremental"))
    conn = warehouse.connect(DB)
    print("fact_shipments rows:", warehouse.fact_count(conn))
    for row in warehouse.total_shipped_by_product(conn):
        print("  %s: %d units, $%.2f" % row)
    conn.close()


if __name__ == "__main__":
    main()
