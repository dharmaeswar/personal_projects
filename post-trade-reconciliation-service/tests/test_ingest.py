"""Tests for multi-source ETL ingest."""

from posttrade.ingest import (
    parse_clearing_csv,
    parse_executions_csv,
    parse_marks_csv,
    parse_text_notes,
)

EXEC_CSV = """exec_id,symbol,side,quantity,price,trade_date,venue,account
E1,AAPL 260117C00250000,BUY,10,4.20,2026-11-24,CBOE,ACC-001
E2,AAPL 260117C00250000,SELL,4,4.50,2026-11-24,CBOE,ACC-001
"""

MARKS_CSV = """symbol,price
AAPL 260117C00250000,4.35
AAPL,251.10
"""

CLEARING_CSV = """clearing_id,symbol,side,quantity,price,trade_date,account,fees
C1,AAPL 260117C00250000,BUY,10,4.20,2026-11-24,ACC-001,1.50
"""


def test_executions_happy_path():
    result = parse_executions_csv(EXEC_CSV)
    assert result.loaded == 2 and result.rejected == 0
    assert result.records[0].exec_id == "E1"
    assert result.records[1].side == "SELL"


def test_executions_quarantine_bad_rows():
    bad = """exec_id,symbol,side,quantity,price,trade_date,venue,account
E1,AAPL,BUY,10,4.20,2026-11-24,CBOE,ACC-001
E1,AAPL,BUY,5,4.20,2026-11-24,CBOE,ACC-001
E2,AAPL,HOLD,5,4.20,2026-11-24,CBOE,ACC-001
E3,AAPL,BUY,0,4.20,2026-11-24,CBOE,ACC-001
E4,AAPL,BUY,5,-1.00,2026-11-24,CBOE,ACC-001
E5,AAPL,BUY,5,4.20,24/11/2026,CBOE,ACC-001
"""
    result = parse_executions_csv(bad)
    assert result.loaded == 1
    assert result.rejected == 5
    reasons = " ".join(q.reason for q in result.quarantined)
    assert "duplicate exec_id E1" in reasons
    assert "bad side" in reasons
    assert "quantity must be positive" in reasons
    assert "price must be positive" in reasons
    assert "bad trade_date" in reasons


def test_marks_happy_path_and_duplicate():
    result = parse_marks_csv(MARKS_CSV + "AAPL,252.00\n")
    assert result.loaded == 2 and result.rejected == 1
    assert result.records["AAPL"] == 251.10  # first mark wins
    assert "duplicate mark" in result.quarantined[0].reason


def test_marks_rejects_bad_price():
    result = parse_marks_csv("symbol,price\nAAPL,not-a-price\n")
    assert result.loaded == 0 and result.rejected == 1


def test_clearing_happy_path():
    result = parse_clearing_csv(CLEARING_CSV)
    assert result.loaded == 1 and result.rejected == 0
    assert result.records[0].fees == 1.50


def test_clearing_negative_fees_quarantined():
    bad = CLEARING_CSV.replace(",1.50", ",-1.50")
    result = parse_clearing_csv(bad)
    assert result.loaded == 0
    assert "fees must not be negative" in result.quarantined[0].reason


def test_text_notes_happy_path():
    result = parse_text_notes(
        "AAPL 260117C00250000: weekly expiry, watch pin risk\nAAPL: earnings next week\n"
    )
    assert result.loaded == 2 and result.rejected == 0
    assert result.records[0] == (
        "AAPL 260117C00250000",
        "weekly expiry, watch pin risk",
    )


def test_text_notes_quarantine_malformed():
    result = parse_text_notes("AAPL: ok\nno colon here\n: empty symbol\n\nMSFT: fine\n")
    assert result.loaded == 2 and result.rejected == 2
    assert result.quarantined[0].row_number == 2
    assert result.quarantined[1].row_number == 3
