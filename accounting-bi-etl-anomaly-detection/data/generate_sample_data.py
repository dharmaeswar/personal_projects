"""Generate the synthetic sample feed (seeded, deterministic).

Run once: python3 data/generate_sample_data.py
Writes data/sample_journals.json — 16 ordinary balanced journals plus
planted cases the pipeline must catch: an unbalanced journal, a duplicate
posting, an amount outlier, a round-dollar entry, a weekend posting, a
late posting into a closed period, and two schema-invalid lines.
"""

import json
import random
from pathlib import Path

random.seed(42)

OUT = Path(__file__).resolve().parent / "sample_journals.json"

# (debit account, credit account, amount range, source system, description)
PATTERNS = [
    ("1100", "4000", (2_000, 45_000), "billing", "Product sale on account"),
    ("1100", "4100", (1_500, 28_000), "billing", "Service revenue on account"),
    ("1000", "1100", (2_000, 40_000), "cash-receipts", "Customer payment received"),
    ("6000", "2000", (6_000, 15_000), "payroll", "Salaries accrued"),
    ("5000", "1200", (3_000, 22_000), "inventory", "Cost of goods sold"),
    ("6100", "2000", (800, 9_500), "expenses", "Marketing spend"),
    ("6200", "2000", (500, 7_500), "expenses", "Office and admin expense"),
    ("7000", "1500", (1_200, 4_800), "fixed-assets", "Monthly depreciation"),
    ("1500", "1000", (1_000, 6_000), "prepaid", "Prepaid expense payment"),
    ("2100", "6000", (2_000, 8_000), "payroll", "Bonus accrual reversal"),
]


def weekday_in_october(day):
    # 2026-10-01 is a Thursday; pick a weekday date in Oct 2026.
    from datetime import date, timedelta

    base = date(2026, 10, 1) + timedelta(days=day - 1)
    while base.weekday() >= 5:
        base += timedelta(days=1)
    return base.isoformat()


def line(entry_id, journal_id, posting_date, period, account, debit, credit, source, desc):
    return {
        "journal_id": journal_id,
        "entry_id": entry_id,
        "posting_date": posting_date,
        "fiscal_period": period,
        "account": account,
        "debit": round(debit, 2),
        "credit": round(credit, 2),
        "currency": "USD",
        "source_system": source,
        "description": desc,
        "posted_by": "auto-post",
    }


def main():
    lines = []
    n = 0
    for i, (dr, cr, (lo, hi), source, desc) in enumerate(PATTERNS):
        n += 1
        journal = f"J-{1000 + i}"
        amount = round(random.uniform(lo, hi), 2)
        day = 1 + (i * 2) % 28
        posting_date = weekday_in_october(day)
        period = posting_date[:7]
        lines.append(line(f"E-{n:04d}", journal, posting_date, period, dr, amount, 0, source, desc))
        n += 1
        lines.append(line(f"E-{n:04d}", journal, posting_date, period, cr, 0, amount, source, desc))
    # Extra ordinary journals so per-account outlier detection has enough data.
    for i in range(6):
        n += 1
        journal = f"J-{2000 + i}"
        amount = round(random.uniform(6_000, 14_000), 2)
        posting_date = weekday_in_october(3 + i * 3)
        lines.append(line(f"E-{n:04d}", journal, posting_date, "2026-10", "6000", amount, 0, "payroll", "Salaries accrued"))
        n += 1
        lines.append(line(f"E-{n:04d}", journal, posting_date, "2026-10", "2000", 0, amount, "payroll", "Salaries accrued"))

    # Planted cases -------------------------------------------------------
    # 1. Amount outlier: $250,000 salaries line among ~$6k-$15k lines.
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3001", "2026-10-14", "2026-10", "6000", 250_000, 0, "payroll", "Executive bonus payout"))
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3001", "2026-10-14", "2026-10", "2000", 0, 250_000, "payroll", "Executive bonus payout"))
    # 2. Round-dollar entry: exactly $50,000.
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3002", "2026-10-15", "2026-10", "6200", 50_000, 0, "expenses", "Consulting fee"))
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3002", "2026-10-15", "2026-10", "2000", 0, 50_000, "expenses", "Consulting fee"))
    # 3. Weekend posting: Saturday 2026-10-17.
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3003", "2026-10-17", "2026-10", "6100", 4_250.75, 0, "expenses", "Weekend campaign spend"))
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3003", "2026-10-17", "2026-10", "2000", 0, 4_250.75, "expenses", "Weekend campaign spend"))
    # 4. Late posting into closed period 2026-08.
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3004", "2026-08-28", "2026-08", "4000", 0, 12_300.50, "billing", "Late August revenue"))
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3004", "2026-08-28", "2026-08", "1100", 12_300.50, 0, "billing", "Late August revenue"))
    # 5. Unbalanced journal: debits exceed credits by $1,000.
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3005", "2026-10-20", "2026-10", "6200", 6_000, 0, "expenses", "Unbalanced test entry"))
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3005", "2026-10-20", "2026-10", "2000", 0, 5_000, "expenses", "Unbalanced test entry"))
    # 6. Duplicate posting: the whole J-1000 journal re-posted under new entry ids.
    first = lines[0]
    second = lines[1]
    n += 1
    dup = dict(first)
    dup["entry_id"] = f"E-{n:04d}"
    lines.append(dup)
    n += 1
    dup2 = dict(second)
    dup2["entry_id"] = f"E-{n:04d}"
    lines.append(dup2)
    # 7. Schema-invalid: unknown account.
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3007", "2026-10-21", "2026-10", "9999", 1_000, 0, "billing", "Unknown account"))
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3007", "2026-10-21", "2026-10", "2000", 0, 1_000, "billing", "Unknown account"))
    # 8. Schema-invalid: both debit and credit set.
    n += 1
    bad = line(f"E-{n:04d}", "J-3008", "2026-10-22", "2026-10", "6200", 500, 500, "expenses", "Both sides set")
    lines.append(bad)
    n += 1
    lines.append(line(f"E-{n:04d}", "J-3008", "2026-10-22", "2026-10", "2000", 0, 500, "expenses", "Both sides set"))

    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"journal_lines": lines}, handle, indent=2)
    print(f"wrote {len(lines)} lines to {OUT}")


if __name__ == "__main__":
    main()
