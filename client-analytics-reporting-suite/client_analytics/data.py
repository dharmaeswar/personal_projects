"""Synthetic client, account, transaction and operations data.

All data is synthetic and seeded (random.Random(42)) so every run
produces the same rows. No real clients, accounts, transactions or
bank data are used, and nothing here claims any affiliation with a
real company.

Planted faults (the validation layer must catch all of them):
  * TXN-0007: negative transaction amount.
  * TXN-0019: amount missing (None).
  * TXN-0042: duplicate of TXN-0003 (same transaction id, new row).
  * ACC-0080: account whose client_id has no matching client (orphan).
"""

import random

MONTHS = ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
CHANNELS = ["Online", "Branch", "Mobile", "Phone"]
SEGMENTS = ["Retail", "Small Business", "Wealth"]
OPS_TYPES = ["Onboarding", "Service Request", "Dispute", "Account Review"]


def generate_clients(rng):
    clients = []
    for i in range(1, 61):
        clients.append({
            "client_id": f"CL-{i:04d}",
            "segment": SEGMENTS[(i - 1) % len(SEGMENTS)],
            "region": ["Northeast", "Southeast", "Midwest", "West"][(i - 1) % 4],
            "join_month": MONTHS[rng.randrange(0, 3)],
        })
    return clients


def generate_accounts(rng, clients):
    accounts = []
    n = 1
    for client in clients:
        for _ in range(rng.choice([1, 1, 2])):
            accounts.append({
                "account_id": f"ACC-{n:04d}",
                "client_id": client["client_id"],
                "account_type": rng.choice(["Checking", "Savings", "Brokerage"]),
                "open_month": client["join_month"],
            })
            n += 1
    # Planted fault: orphan account, client does not exist.
    accounts.append({
        "account_id": f"ACC-{n:04d}",
        "client_id": "CL-9999",
        "account_type": "Checking",
        "open_month": "2026-06",
    })
    return accounts


def generate_transactions(rng, accounts):
    txns = []
    n = 1
    for month in MONTHS:
        for _ in range(100):
            account = rng.choice(accounts)
            amount = round(rng.uniform(25.0, 8500.0), 2)
            txns.append({
                "txn_id": f"TXN-{n:04d}",
                "account_id": account["account_id"],
                "month": month,
                "channel": rng.choice(CHANNELS),
                "txn_type": rng.choice(["Deposit", "Withdrawal", "Transfer", "Payment"]),
                "amount": amount,
            })
            n += 1
    # Planted faults.
    txns[6]["amount"] = -120.50                      # TXN-0007 negative
    txns[18]["amount"] = None                       # TXN-0019 missing
    dup = dict(txns[2])                             # TXN-0003 duplicated
    dup["amount"] = 410.00
    txns.append(dup)
    return txns


def generate_ops_events(rng, clients):
    events = []
    for i in range(1, 121):
        client = rng.choice(clients)
        events.append({
            "event_id": f"OPS-{i:04d}",
            "client_id": client["client_id"],
            "month": rng.choice(MONTHS),
            "event_type": rng.choice(OPS_TYPES),
            "resolution_days": rng.randrange(1, 15),
        })
    return events


def generate():
    rng = random.Random(42)
    clients = generate_clients(rng)
    accounts = generate_accounts(rng, clients)
    transactions = generate_transactions(rng, accounts)
    ops_events = generate_ops_events(rng, clients)
    return {
        "clients": clients,
        "accounts": accounts,
        "transactions": transactions,
        "ops_events": ops_events,
    }
