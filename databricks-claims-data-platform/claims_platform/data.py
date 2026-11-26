"""Seeded synthetic member and claims data.

All data is synthetic (seed 42). No real member, patient, claim, or PHI data
is used, and nothing here is a claim about any real insurer or person.
"""
import numpy as np
import pandas as pd

SEED = 42
PLANS = ["Medicare Advantage", "Medicaid", "Commercial PPO", "Commercial HMO"]
STATES = ["KY", "OH", "IN", "TN", "FL", "TX"]
DIAG_GROUPS = ["Cardiology", "Orthopedics", "Oncology", "Primary Care", "Behavioral Health"]
DIAG_CODES = {"Cardiology": "I25", "Orthopedics": "M17", "Oncology": "C50",
              "Primary Care": "Z00", "Behavioral Health": "F32"}


def make_members(n=120, seed=SEED):
    rng = np.random.default_rng(seed)
    members = pd.DataFrame({
        "member_id": [f"M{i:04d}" for i in range(1, n + 1)],
        "plan": rng.choice(PLANS, size=n),
        "state": rng.choice(STATES, size=n),
        "enrolled_date": pd.to_datetime(
            rng.choice(pd.date_range("2024-01-01", "2025-06-30"), size=n)),
        "age_band": rng.choice(["18-34", "35-49", "50-64", "65+"], size=n),
    })
    return members


def make_claims(n_clean=300, seed=SEED):
    """300 clean claims + 24 planted defects (duplicates, nulls, bad values)."""
    rng = np.random.default_rng(seed)
    base = pd.DataFrame({
        "claim_id": [f"C{i:05d}" for i in range(1, n_clean + 1)],
        "member_id": [f"M{int(i):04d}" for i in rng.integers(1, 121, size=n_clean)],
        "service_date": pd.to_datetime(
            rng.choice(pd.date_range("2026-09-01", "2026-11-15"), size=n_clean)),
        "diag_group": rng.choice(DIAG_GROUPS, size=n_clean),
        "billed_amount": np.round(rng.uniform(120, 8500, size=n_clean), 2),
        "ingested_at": pd.to_datetime("2026-11-20 06:00:00")
        + pd.to_timedelta(rng.integers(0, 600, size=n_clean), unit="m"),
    })
    base["diag_code"] = base["diag_group"].map(DIAG_CODES)
    base["adjustment"] = np.round(base["billed_amount"] * rng.uniform(0.05, 0.25, size=n_clean), 2)
    base["paid_amount"] = np.round(base["billed_amount"] - base["adjustment"], 2)

    defects = []
    # 4 duplicate claim_ids (later ingested_at wins)
    dup = base.iloc[:4].copy()
    dup["ingested_at"] = dup["ingested_at"] + pd.Timedelta(hours=2)
    dup["paid_amount"] = dup["paid_amount"] + 1.00
    defects.append(dup)
    # 5 null member_id
    nullm = base.iloc[4:9].copy()
    nullm["member_id"] = None
    nullm["claim_id"] = [f"C9{i:03d}" for i in range(1, 6)]
    defects.append(nullm)
    # 4 negative paid amounts
    neg = base.iloc[9:13].copy()
    neg["paid_amount"] = -np.abs(neg["paid_amount"])
    neg["claim_id"] = [f"C9{i:03d}" for i in range(11, 15)]
    defects.append(neg)
    # 3 unknown diagnosis codes
    unk = base.iloc[13:16].copy()
    unk["diag_code"] = "XXX"
    unk["claim_id"] = [f"C9{i:03d}" for i in range(21, 24)]
    defects.append(unk)
    # 3 future service dates
    fut = base.iloc[16:19].copy()
    fut["service_date"] = pd.to_datetime("2027-03-01")
    fut["claim_id"] = [f"C9{i:03d}" for i in range(31, 34)]
    defects.append(fut)
    # 5 paid != billed - adjustment
    mis = base.iloc[19:24].copy()
    mis["paid_amount"] = mis["paid_amount"] + 57.25
    mis["claim_id"] = [f"C9{i:03d}" for i in range(41, 46)]
    defects.append(mis)

    raw = pd.concat([base] + defects, ignore_index=True)
    return raw.sample(frac=1.0, random_state=seed).reset_index(drop=True)


if __name__ == "__main__":
    print(make_members().head(3).to_string(index=False))
    print(make_claims().shape)
