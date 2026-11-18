"""Anomaly detection on journal-entry lines.

Every check is a rule the Accounting BI team can explain to an auditor:
no black-box model. A flagged line is still real data — it is excluded
from nothing by itself, it is reported so a human can review it.
"""

import math
import statistics
from datetime import date

from .contracts import CHART_OF_ACCOUNTS, CLOSED_PERIODS

ROUND_THRESHOLD = 5000.0  # round-dollar amounts at or above this are flagged
OUTLIER_Z = 3.5  # modified z-score (median / MAD) cutoff per account


def amount_of(line):
    return float(line["debit"] or line["credit"])


def detect_outliers(lines):
    """Per-account amount outliers via median and MAD (modified z-score).

    Needs at least 5 lines in an account and a non-zero MAD; otherwise the
    account is too thin to judge. Returns {entry_id: detail}.
    """
    by_account = {}
    for line in lines:
        by_account.setdefault(line["account"], []).append(line)
    flagged = {}
    for account, group in by_account.items():
        if len(group) < 5:
            continue
        amounts = [amount_of(line) for line in group]
        median = statistics.median(amounts)
        mad = statistics.median([abs(a - median) for a in amounts])
        if mad == 0:
            continue
        for line in group:
            z = 0.6745 * (amount_of(line) - median) / mad
            if abs(z) > OUTLIER_Z:
                flagged[line["entry_id"]] = (
                    f"amount outlier in account {account}: "
                    f"${amount_of(line):,.2f} vs median ${median:,.2f} (modified z={z:.1f})"
                )
    return flagged


def detect_round_numbers(lines):
    """Round-dollar postings: whole thousands at or above the threshold.

    A single round number is normal; a pattern of them near close is a
    classic manual-adjustment signal, so each one is listed for review.
    """
    flagged = {}
    for line in lines:
        amount = amount_of(line)
        if amount >= ROUND_THRESHOLD and amount % 1000 == 0:
            flagged[line["entry_id"]] = f"round-dollar amount ${amount:,.2f}"
    return flagged


def detect_weekend_postings(lines):
    """Postings dated Saturday or Sunday."""
    flagged = {}
    for line in lines:
        year, month, day = (int(part) for part in line["posting_date"].split("-"))
        if date(year, month, day).weekday() >= 5:
            flagged[line["entry_id"]] = f"weekend posting on {line['posting_date']}"
    return flagged


def detect_late_postings(lines):
    """Lines posted into a fiscal period that is already closed."""
    flagged = {}
    for line in lines:
        if line["fiscal_period"] in CLOSED_PERIODS:
            flagged[line["entry_id"]] = f"posted into closed period {line['fiscal_period']}"
    return flagged


BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


def benford_check(lines):
    """First-digit distribution of amounts vs Benford's law.

    Returns {digit: (observed share, expected share)} and the largest
    absolute deviation. A large deviation does not prove fraud — it says
    the population is worth a closer look before close.
    """
    digits = {}
    total = 0
    for line in lines:
        amount = amount_of(line)
        if amount <= 0:
            continue
        first = int(str(amount).lstrip("0.")[0]) if amount >= 1 else int(str(amount).split(".")[1].lstrip("0")[0])
        digits[first] = digits.get(first, 0) + 1
        total += 1
    if total == 0:
        return {}, 0.0
    result = {}
    max_dev = 0.0
    for digit in range(1, 10):
        observed = digits.get(digit, 0) / total
        result[digit] = (round(observed, 4), round(BENFORD_EXPECTED[digit], 4))
        max_dev = max(max_dev, abs(observed - BENFORD_EXPECTED[digit]))
    return result, round(max_dev, 4)


def run_all_checks(lines):
    """Run every anomaly check. Returns {entry_id: [flag details]}."""
    checks = [
        detect_outliers(lines),
        detect_round_numbers(lines),
        detect_weekend_postings(lines),
        detect_late_postings(lines),
    ]
    merged = {}
    for flagged in checks:
        for entry_id, detail in flagged.items():
            merged.setdefault(entry_id, []).append(detail)
    return merged
