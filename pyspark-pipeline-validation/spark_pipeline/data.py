"""Synthetic raw event data for the pipeline.

All data is synthetic and seeded (seed 42), so every run produces the same
240 raw rows. 18 rows are planted defects on purpose:

- 4 duplicate event_ids (extra copies of clean rows)
- 5 null user_ids
- 3 negative amounts
- 3 unknown product_codes
- 2 event_dates outside the allowed window (future dates)
- 1 amount that does not equal quantity * unit_price
"""
import numpy as np
import pandas as pd

SEED = 42
N_CLEAN = 222
ALLOWED_START = "2026-10-01"
ALLOWED_END = "2026-11-17"

PRODUCT_DIM = pd.DataFrame(
    [
        {"product_code": "P100", "product_category": "Electronics", "unit_price": 49.99},
        {"product_code": "P200", "product_category": "Apparel", "unit_price": 29.99},
        {"product_code": "P300", "product_category": "Home", "unit_price": 19.99},
        {"product_code": "P400", "product_category": "Sports", "unit_price": 39.99},
    ]
)

REGIONS = ["North", "South", "East", "West"]
CHANNELS = ["web", "mobile", "store"]


def generate_raw(n_clean=N_CLEAN, seed=SEED):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(ALLOWED_START, ALLOWED_END, freq="D")
    products = PRODUCT_DIM["product_code"].tolist()
    price = dict(zip(PRODUCT_DIM["product_code"], PRODUCT_DIM["unit_price"]))

    rows = []
    for i in range(n_clean):
        code = products[i % len(products)]
        qty = int(rng.integers(1, 6))
        rows.append(
            {
                "event_id": f"EVT-{i + 1:06d}",
                "user_id": f"U{int(rng.integers(1000, 9999))}",
                "product_code": code,
                "region": REGIONS[i % len(REGIONS)],
                "channel": CHANNELS[i % len(CHANNELS)],
                "event_date": str(dates[i % len(dates)].date()),
                "quantity": qty,
                "unit_price": price[code],
                "amount": round(qty * price[code], 2),
                "ingested_at": f"2026-11-17T08:{i % 60:02d}:00",
            }
        )
    df = pd.DataFrame(rows)

    defects = []
    # 4 duplicates: exact copies of clean rows 0-3 (later ingested_at wins the dedup).
    for i in range(4):
        dup = df.iloc[i].copy()
        dup["ingested_at"] = "2026-11-17T09:00:00"
        defects.append(dup)
    # 5 null user_id
    for i in range(5):
        bad = df.iloc[10 + i].copy()
        bad["event_id"] = f"EVT-BAD-U{i + 1}"
        bad["user_id"] = None
        defects.append(bad)
    # 3 negative amounts
    for i in range(3):
        bad = df.iloc[20 + i].copy()
        bad["event_id"] = f"EVT-BAD-N{i + 1}"
        bad["amount"] = -abs(bad["amount"])
        defects.append(bad)
    # 3 unknown product codes
    for i in range(3):
        bad = df.iloc[30 + i].copy()
        bad["event_id"] = f"EVT-BAD-P{i + 1}"
        bad["product_code"] = "P999"
        defects.append(bad)
    # 2 future event dates
    for i in range(2):
        bad = df.iloc[40 + i].copy()
        bad["event_id"] = f"EVT-BAD-D{i + 1}"
        bad["event_date"] = "2027-01-15"
        defects.append(bad)
    # 1 wrong amount (quantity * unit_price mismatch)
    bad = df.iloc[50].copy()
    bad["event_id"] = "EVT-BAD-A1"
    bad["amount"] = round(bad["amount"] + 10.00, 2)
    defects.append(bad)

    raw = pd.concat([df, pd.DataFrame(defects)], ignore_index=True)
    return raw
