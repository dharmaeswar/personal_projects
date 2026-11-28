"""Synthetic, seeded source data for a regulated long-term savings program.

All data is synthetic (seed 42). No real account holder, child, or program
data is used, and nothing here is a claim about any real institution or
government program.
"""
import numpy as np
import pandas as pd

SEED = 42

PROGRAMS = ["core-savings", "education-savings"]
STATES = ["NY", "PA", "OH", "NJ", "CT"]


def make_accounts(n=120, seed=SEED):
    """Synthetic savings accounts: one row per account."""
    rng = np.random.default_rng(seed)
    accounts = pd.DataFrame({
        "account_id": [f"ACC-{i:05d}" for i in range(1, n + 1)],
        "holder_id": [f"H-{i:05d}" for i in range(1, n + 1)],
        "program": rng.choice(PROGRAMS, size=n),
        "state": rng.choice(STATES, size=n),
        "enrollment_date": pd.to_datetime(
            rng.choice(pd.date_range("2024-01-01", "2026-10-31"), size=n)),
        "status": rng.choice(
            ["active", "active", "active", "suspended", "closed"],
            size=n),
        "birth_year": rng.integers(2015, 2026, size=n),
    })
    return accounts


def make_contribution_batch(accounts, n=600, seed=SEED, bad_frac=0.04):
    """Batch contribution file: one row per contribution.

    A small seeded share of rows is deliberately bad (negative amount,
    missing account, bad date) so the pipeline's quarantine path is exercised.
    """
    rng = np.random.default_rng(seed + 1)
    acct = rng.choice(accounts["account_id"], size=n)
    amounts = np.round(rng.normal(250, 120, size=n), 2)
    dates = rng.choice(pd.date_range("2025-01-01", "2026-11-20"), size=n)
    batch = pd.DataFrame({
        "event_id": [f"BATCH-{i:06d}" for i in range(1, n + 1)],
        "account_id": acct,
        "event_type": "contribution",
        "amount": amounts,
        "event_date": pd.to_datetime(dates),
        "source": "batch-file",
        "ingested_at": pd.Timestamp("2026-11-28 08:00:00"),
    })
    # Seeded bad rows: negative amounts, unknown accounts, bad dates.
    n_bad = int(n * bad_frac)
    bad_idx = rng.choice(batch.index, size=n_bad, replace=False)
    batch.loc[bad_idx[:8], "amount"] = -np.round(
        rng.uniform(10, 500, size=8), 2)
    batch.loc[bad_idx[8:16], "account_id"] = "ACC-99999"
    batch.loc[bad_idx[16:], "event_date"] = pd.NaT
    # Seeded duplicates: re-delivered rows with a later ingest time.
    dup = batch.iloc[:12].copy()
    dup["ingested_at"] = pd.Timestamp("2026-11-28 09:00:00")
    return pd.concat([batch, dup], ignore_index=True)


def make_stream_events(accounts, n=300, seed=SEED):
    """Kafka-style event stream: enrollment, contribution, disbursement events.

    Stored locally as a JSON-lines event log; in production this is a Kafka
    topic consumed by a Spark Structured Streaming job.
    """
    rng = np.random.default_rng(seed + 2)
    acct = rng.choice(accounts["account_id"], size=n)
    types = rng.choice(
        ["contribution", "contribution", "contribution",
         "disbursement", "enrollment"],
        size=n)
    amounts = np.where(
        types == "disbursement",
        np.round(rng.normal(400, 150, size=n), 2),
        np.round(rng.normal(250, 120, size=n), 2))
    events = pd.DataFrame({
        "event_id": [f"EVT-{i:06d}" for i in range(1, n + 1)],
        "account_id": acct,
        "event_type": types,
        "amount": amounts,
        "event_date": pd.to_datetime(rng.choice(
            pd.date_range("2025-06-01", "2026-11-27"), size=n)),
        "source": "kafka-topic/savings-events",
        "ingested_at": pd.Timestamp("2026-11-28 08:30:00"),
    })
    # One seeded duplicate delivery (same event_id, later ingest).
    dup = events.iloc[:5].copy()
    dup["ingested_at"] = pd.Timestamp("2026-11-28 10:00:00")
    return pd.concat([events, dup], ignore_index=True)


def make_investments(accounts, n=240, seed=SEED):
    """Investment holdings per account (fund, units, value date)."""
    rng = np.random.default_rng(seed + 3)
    funds = ["us-equity-index", "treasury-bond", "balanced-fund"]
    return pd.DataFrame({
        "account_id": rng.choice(accounts["account_id"], size=n),
        "fund": rng.choice(funds, size=n),
        "units": np.round(rng.uniform(1, 200, size=n), 4),
        "unit_price": np.round(rng.uniform(10, 120, size=n), 2),
        "value_date": pd.to_datetime(rng.choice(
            pd.date_range("2026-10-01", "2026-11-27"), size=n)),
    })
