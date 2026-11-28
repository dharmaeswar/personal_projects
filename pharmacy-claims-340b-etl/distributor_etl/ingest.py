"""Distributor ETL: ingest shipment, inventory and customer feeds.

The distributor side of the pharmacy supply chain: a pharmaceutical
distributor receives shipment records (CSV), inventory/pricing (JSON)
and a customer master (CSV) from disparate sources and normalises them
to typed records. Malformed rows are reported, never silently dropped.
"""

import csv
import json


def parse_shipments(path):
    """Parse the shipment feed (CSV) into typed dicts."""
    shipments, errors = [], []
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            try:
                shipments.append({
                    "shipment_id": row["shipment_id"].strip(),
                    "customer_id": row["customer_id"].strip(),
                    "product_id": row["product_id"].strip(),
                    "quantity": int(row["quantity"]),
                    "ship_date": row["ship_date"].strip(),
                    "amount": float(row["amount"]),
                    "warehouse_id": row["warehouse_id"].strip(),
                })
            except (KeyError, ValueError) as exc:
                errors.append("malformed shipment row %r: %s" % (row, exc))
    return shipments, errors


def parse_inventory(path):
    """Parse the inventory/pricing feed (JSON) keyed by product_id."""
    with open(path) as fh:
        raw = json.load(fh)
    return {item["product_id"]: {"product_name": item["product_name"],
                                 "unit_price": float(item["unit_price"]),
                                 "on_hand": int(item["on_hand"])}
            for item in raw["products"]}


def parse_customers(path):
    """Parse the customer master (CSV) keyed by customer_id."""
    customers = {}
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            customers[row["customer_id"].strip()] = {
                "customer_id": row["customer_id"].strip(),
                "name": row["name"].strip(),
                "active": row["active"].strip(),
                "contract_start": row["contract_start"].strip(),
                "contract_end": row["contract_end"].strip(),
            }
    return customers
