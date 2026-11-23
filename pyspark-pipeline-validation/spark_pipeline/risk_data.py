"""Synthetic risk-exposure events for the Risk Technology ETL module.

All data is synthetic and seeded (seed 7), so every run produces the same
165 raw rows: 150 clean trades plus 15 planted defects on purpose:

- 3 duplicate trade_ids (extra copies of clean rows)
- 4 null counterparties
- 3 negative notionals
- 2 unknown books
- 2 trade_dates outside the allowed window (future dates)
- 1 exposure that does not equal notional * instrument risk factor

Nothing here is real JPMorgan, market, or counterparty data, and nothing
here is a claim about any real institution.
"""
import numpy as np
import pandas as pd

SEED = 7
N_CLEAN = 150
ALLOWED_START = "2026-10-01"
ALLOWED_END = "2026-11-17"

BOOK_DIM = pd.DataFrame(
    [
        {"book": "RATES", "desk": "Rates Trading", "region": "North America"},
        {"book": "CREDIT", "desk": "Credit Trading", "region": "North America"},
        {"book": "FX", "desk": "FX Trading", "region": "Europe"},
        {"book": "EQUITY", "desk": "Equity Derivatives", "region": "Asia"},
    ]
)

# Per-instrument risk factor: exposure = notional * factor (Spark SQL
# equivalent: `exposure = notional * factor` in a withColumn expression).
INSTRUMENT_FACTOR = {
    "IRS": 0.02,
    "CDS": 0.05,
    "FXFwd": 0.01,
    "EQOpt": 0.03,
}

INSTRUMENTS = ["IRS", "CDS", "FXFwd", "EQOpt"]
BOOKS = ["RATES", "CREDIT", "FX", "EQUITY"]
CURRENCIES = ["USD", "EUR", "GBP", "JPY"]


def generate_risk_raw(n_clean=N_CLEAN, seed=SEED):
    rng = np.random.default_rng(seed)
    dates = pd.date_range(ALLOWED_START, ALLOWED_END, freq="D")

    rows = []
    for i in range(n_clean):
        instrument = INSTRUMENTS[i % len(INSTRUMENTS)]
        book = BOOKS[i % len(BOOKS)]
        notional = round(float(rng.uniform(1_000_000, 50_000_000)), 2)
        rows.append(
            {
                "trade_id": f"TRD-{i + 1:06d}",
                "book": book,
                "counterparty": f"CP{int(rng.integers(1000, 9999))}",
                "instrument_type": instrument,
                "notional": notional,
                "currency": CURRENCIES[i % len(CURRENCIES)],
                "trade_date": str(dates[i % len(dates)].date()),
                "exposure": round(notional * INSTRUMENT_FACTOR[instrument], 2),
                "ingested_at": f"2026-11-17T08:{i % 60:02d}:00",
            }
        )
    df = pd.DataFrame(rows)

    defects = []
    # 3 duplicates: exact copies of clean rows 0-2 (later ingested_at wins the dedup).
    for i in range(3):
        dup = df.iloc[i].copy()
        dup["ingested_at"] = "2026-11-17T09:00:00"
        defects.append(dup)
    # 4 null counterparties
    for i in range(4):
        bad = df.iloc[10 + i].copy()
        bad["trade_id"] = f"TRD-BAD-C{i + 1}"
        bad["counterparty"] = None
        defects.append(bad)
    # 3 negative notionals
    for i in range(3):
        bad = df.iloc[20 + i].copy()
        bad["trade_id"] = f"TRD-BAD-N{i + 1}"
        bad["notional"] = -abs(bad["notional"])
        bad["exposure"] = round(bad["notional"] * INSTRUMENT_FACTOR[bad["instrument_type"]], 2)
        defects.append(bad)
    # 2 unknown books
    for i in range(2):
        bad = df.iloc[30 + i].copy()
        bad["trade_id"] = f"TRD-BAD-B{i + 1}"
        bad["book"] = "CRYPTO"
        defects.append(bad)
    # 2 future trade dates
    for i in range(2):
        bad = df.iloc[40 + i].copy()
        bad["trade_id"] = f"TRD-BAD-D{i + 1}"
        bad["trade_date"] = "2027-01-15"
        defects.append(bad)
    # 1 exposure mismatch (notional * factor + 10,000)
    bad = df.iloc[50].copy()
    bad["trade_id"] = "TRD-BAD-E1"
    bad["exposure"] = round(bad["exposure"] + 10_000.00, 2)
    defects.append(bad)

    raw = pd.concat([df, pd.DataFrame(defects)], ignore_index=True)
    return raw
