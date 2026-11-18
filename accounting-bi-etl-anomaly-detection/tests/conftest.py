import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_line(**overrides):
    line = {
        "journal_id": "J-1",
        "entry_id": "E-0001",
        "posting_date": "2026-10-05",  # a Monday
        "fiscal_period": "2026-10",
        "account": "6000",
        "debit": 1000.0,
        "credit": 0.0,
        "currency": "USD",
        "source_system": "payroll",
        "description": "Salaries accrued",
        "posted_by": "auto-post",
    }
    line.update(overrides)
    return line
