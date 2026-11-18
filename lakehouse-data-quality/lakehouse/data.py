"""Synthetic source data for the bronze layer.

All data is generated from a fixed seed, so every run produces the same
tables. The orders table plants 13 bad rows on purpose so the pipeline and
the checks have real violations to catch:

- 3 duplicate order_id values
- 4 null customer_id values
- 2 negative quantity values
- 2 product_id values that do not exist in the products table
- 1 order_date in the future (outside the allowed window)
- 1 total_amount that does not equal quantity * unit_price
"""

from __future__ import annotations

import numpy as np
import pandas as pd

N_CUSTOMERS = 40
N_PRODUCTS = 12
N_ORDERS = 200

REGIONS = ["Northeast", "Midwest", "South", "West"]
CATEGORIES = ["Electronics", "Home", "Apparel", "Grocery"]

# (column, kind) pairs describing each planted violation.
PLANTED_VIOLATIONS = {
    "duplicate_order_id": 3,
    "null_customer_id": 4,
    "negative_quantity": 2,
    "unknown_product_id": 2,
    "future_order_date": 1,
    "wrong_total": 1,
}


def _rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_customers(seed: int = 42) -> pd.DataFrame:
    rng = _rng(seed)
    return pd.DataFrame(
        {
            "customer_id": [f"C{i:04d}" for i in range(1, N_CUSTOMERS + 1)],
            "customer_name": [f"Customer {i}" for i in range(1, N_CUSTOMERS + 1)],
            "region": rng.choice(REGIONS, size=N_CUSTOMERS),
            "signup_date": pd.to_datetime(
                rng.choice(pd.date_range("2023-01-01", "2025-06-30"), size=N_CUSTOMERS)
            ),
        }
    )


def generate_products(seed: int = 42) -> pd.DataFrame:
    rng = _rng(seed)
    return pd.DataFrame(
        {
            "product_id": [f"P{i:03d}" for i in range(1, N_PRODUCTS + 1)],
            "product_name": [f"Product {i}" for i in range(1, N_PRODUCTS + 1)],
            "category": rng.choice(CATEGORIES, size=N_PRODUCTS),
            "list_price": np.round(rng.uniform(5.0, 250.0, size=N_PRODUCTS), 2),
        }
    )


def generate_orders(seed: int = 42) -> pd.DataFrame:
    """Clean base orders; violations are planted by :func:`plant_violations`."""
    rng = _rng(seed)
    customers = [f"C{i:04d}" for i in range(1, N_CUSTOMERS + 1)]
    products = [f"P{i:03d}" for i in range(1, N_PRODUCTS + 1)]
    order_ids = [f"O{i:05d}" for i in range(1, N_ORDERS + 1)]
    quantities = rng.integers(1, 10, size=N_ORDERS)
    prices = np.round(rng.uniform(5.0, 250.0, size=N_ORDERS), 2)
    return pd.DataFrame(
        {
            "order_id": order_ids,
            "customer_id": rng.choice(customers, size=N_ORDERS),
            "product_id": rng.choice(products, size=N_ORDERS),
            "order_date": pd.to_datetime(
                rng.choice(pd.date_range("2026-01-01", "2026-11-17"), size=N_ORDERS)
            ),
            "quantity": quantities,
            "unit_price": prices,
            "total_amount": np.round(quantities * prices, 2),
            "region": rng.choice(REGIONS, size=N_ORDERS),
        }
    )


def plant_violations(orders: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``orders`` with the 12 planted violations applied."""
    bad = orders.copy()
    # 3 duplicate order ids: copy rows 0-2 over rows 10-12 with new positions.
    for i, src in enumerate((0, 1, 2)):
        bad.loc[10 + i, "order_id"] = bad.loc[src, "order_id"]
    # 4 null customer ids.
    bad.loc[20:23, "customer_id"] = None
    # 2 negative quantities (totals recomputed so only the range check fires).
    bad.loc[30, "quantity"] = -2
    bad.loc[31, "quantity"] = -5
    bad.loc[30, "total_amount"] = round(-2 * bad.loc[30, "unit_price"], 2)
    bad.loc[31, "total_amount"] = round(-5 * bad.loc[31, "unit_price"], 2)
    # 2 unknown product ids.
    bad.loc[40, "product_id"] = "P999"
    bad.loc[41, "product_id"] = "P998"
    # 1 future order date.
    bad.loc[50, "order_date"] = pd.Timestamp("2027-06-01")
    # 1 wrong total (quantity and price are fine, the total is not).
    bad.loc[60, "total_amount"] = round(bad.loc[60, "total_amount"] + 10.0, 2)
    return bad


def generate_bronze(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Generate the full bronze layer: customers, products, orders (with violations)."""
    return {
        "customers": generate_customers(seed),
        "products": generate_products(seed),
        "orders": plant_violations(generate_orders(seed)),
    }
