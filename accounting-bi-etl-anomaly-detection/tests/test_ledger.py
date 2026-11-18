from conftest import make_line
from src import ledger


def _db(tmp_path):
    return ledger.open_db(tmp_path / "test.db")


def _balanced_journal(journal="J-1", amount=1000.0, date="2026-10-05"):
    return [
        make_line(journal_id=journal, entry_id=f"{journal}-D", posting_date=date, account="6000", debit=amount, credit=0),
        make_line(journal_id=journal, entry_id=f"{journal}-C", posting_date=date, account="2000", debit=0, credit=amount),
    ]


def test_balanced_journal_passes(tmp_path):
    conn = _db(tmp_path)
    ledger.insert_lines(conn, _balanced_journal())
    assert ledger.check_journal_balances(conn) == []


def test_unbalanced_journal_flagged(tmp_path):
    conn = _db(tmp_path)
    lines = _balanced_journal()
    lines[1]["credit"] = 900.0  # short by 100
    ledger.insert_lines(conn, lines)
    unbalanced = ledger.check_journal_balances(conn)
    assert len(unbalanced) == 1 and unbalanced[0][0] == "J-1"


def test_trial_balance_balances(tmp_path):
    conn = _db(tmp_path)
    ledger.insert_lines(conn, _balanced_journal("J-1", 1000.0) + _balanced_journal("J-2", 2500.0, "2026-10-06"))
    ledger.check_journal_balances(conn)
    clean = ledger.clean_entry_ids(conn)
    tb = ledger.trial_balance(conn, clean)
    assert round(sum(r["debit"] for r in tb), 2) == round(sum(r["credit"] for r in tb), 2) == 3500.0
    assert {r["account"] for r in tb} == {"6000", "2000"}


def test_duplicate_content_line_excluded_from_gold(tmp_path):
    conn = _db(tmp_path)
    lines = _balanced_journal()
    dup_d = dict(lines[0])
    dup_d["entry_id"] = "J-1-D-copy"
    dup_c = dict(lines[1])
    dup_c["entry_id"] = "J-1-C-copy"
    ledger.insert_lines(conn, lines + [dup_d, dup_c])
    ledger.check_journal_balances(conn)
    assert ledger.find_duplicates(conn) == ["J-1-C-copy", "J-1-D-copy"]
    clean = ledger.clean_entry_ids(conn)
    assert sorted(clean) == ["J-1-C", "J-1-D"]


def test_unbalanced_journal_excluded_from_gold(tmp_path):
    conn = _db(tmp_path)
    good = _balanced_journal("J-1", 1000.0)
    bad = _balanced_journal("J-2", 2000.0, "2026-10-06")
    bad[1]["credit"] = 1500.0
    ledger.insert_lines(conn, good + bad)
    ledger.check_journal_balances(conn)
    clean = ledger.clean_entry_ids(conn)
    assert sorted(clean) == ["J-1-C", "J-1-D"]


def test_quarantine_records_reason(tmp_path):
    conn = _db(tmp_path)
    ledger.quarantine_line(conn, make_line(account="9999"), "unknown account: 9999")
    rows = conn.execute("SELECT reason FROM quarantine").fetchall()
    assert rows == [("unknown account: 9999",)]
