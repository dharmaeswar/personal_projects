"""Data contracts for journal-entry lines.

Every line arriving from a subledger feed must satisfy this schema before
it can enter the ledger. Validation failures are quarantined with a reason,
never dropped silently.
"""

REQUIRED_FIELDS = {
    "journal_id": str,
    "entry_id": str,
    "posting_date": str,  # ISO YYYY-MM-DD
    "fiscal_period": str,  # YYYY-MM
    "account": str,  # chart-of-accounts code, e.g. "1000"
    "debit": (int, float),
    "credit": (int, float),
    "currency": str,
    "source_system": str,
}

# Synthetic chart of accounts used by this project. Real ledgers have a
# published chart; here it is the allow-list that rejects stray accounts.
CHART_OF_ACCOUNTS = {
    "1000": "Cash and Equivalents",
    "1100": "Accounts Receivable",
    "1200": "Inventory",
    "1500": "Prepaid Expenses",
    "2000": "Accounts Payable",
    "2100": "Accrued Expenses",
    "2200": "Deferred Revenue",
    "3000": "Common Stock",
    "3100": "Retained Earnings",
    "4000": "Product Revenue",
    "4100": "Service Revenue",
    "5000": "Cost of Goods Sold",
    "6000": "Salaries and Benefits",
    "6100": "Marketing Expense",
    "6200": "General and Administrative",
    "7000": "Depreciation Expense",
}

# Periods already closed. A line dated into a closed period is a late
# posting: valid data, but it must be flagged for the close team.
CLOSED_PERIODS = {"2026-07", "2026-08"}
CURRENT_PERIOD = "2026-10"


def validate_line(line):
    """Return a list of validation errors for one journal line (empty = OK)."""
    errors = []
    if not isinstance(line, dict):
        return ["line is not an object"]
    for field, types in REQUIRED_FIELDS.items():
        if field not in line:
            errors.append(f"missing field: {field}")
        elif not isinstance(line[field], types) or isinstance(line[field], bool):
            errors.append(f"wrong type for field: {field}")
    if errors:
        return errors
    if line["debit"] < 0 or line["credit"] < 0:
        errors.append("negative amount")
    if line["debit"] == 0 and line["credit"] == 0:
        errors.append("zero-amount line")
    if line["debit"] > 0 and line["credit"] > 0:
        errors.append("both debit and credit set")
    if line["account"] not in CHART_OF_ACCOUNTS:
        errors.append(f"unknown account: {line['account']}")
    if line["currency"] != "USD":
        errors.append(f"unsupported currency: {line['currency']}")
    date = line["posting_date"]
    if len(date) != 10 or date[4] != "-" or date[7] != "-":
        errors.append("posting_date is not YYYY-MM-DD")
    elif date[:7] != line["fiscal_period"]:
        errors.append("posting_date does not match fiscal_period")
    return errors
