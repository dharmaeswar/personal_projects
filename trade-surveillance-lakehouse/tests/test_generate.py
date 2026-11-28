"""Generate stage: deterministic seed, planted defects, wash pattern."""
from __future__ import annotations

import pandas as pd

from surveillance_lakehouse import generate as gen


def test_generate_is_deterministic():
    a = gen.generate()
    b = gen.generate()
    for name in ("orders", "executions", "trades"):
        pd.testing.assert_frame_equal(a[name], b[name])


def test_generate_counts_and_columns():
    feeds = gen.generate()
    assert list(feeds["orders"].columns) == gen.ORDER_COLUMNS
    assert list(feeds["executions"].columns) == gen.EXEC_COLUMNS
    assert list(feeds["trades"].columns) == gen.TRADE_COLUMNS
    # 400 orders/day + 8 planted wash orders/day = 2,040, plus 12 defects
    assert len(feeds["orders"]) == 2052
    assert len(feeds["trades"]) == 1500
    assert 1200 < len(feeds["executions"]) < 1500


def test_planted_defects_present():
    orders = gen.generate()["orders"]
    # All 12 planted defect rows share an order_id with a real row:
    # 5 re-sent duplicates + 3 missing-account + 2 bad-qty + 2 date-mismatch.
    assert orders["order_id"].duplicated().sum() == 12
    assert orders["account_id"].isna().sum() == 3      # missing account
    assert (orders["qty"] <= 0).sum() == 2             # bad quantity
    ts_date = pd.to_datetime(orders["order_ts"]).dt.date
    assert (ts_date != orders["trade_date"]).sum() == 2  # date mismatch
    # 7 order_ids carry two distinct quantities: the 5 re-sent
    # duplicates (qty + 10) and the 2 bad-quantity copies (qty set to 0).
    dupes = orders[orders.duplicated(subset=["order_id"], keep=False)]
    assert (dupes.groupby("order_id")["qty"].nunique() == 2).sum() == 7


def test_planted_wash_pattern_present():
    orders = gen.generate()["orders"]
    wash = orders[(orders["account_id"] == "ACC-007")
                  & (orders["symbol"] == "AAPL")
                  & (orders["event"] == "NEW")]
    for day in gen.DAYS:
        day_rows = wash[wash["trade_date"] == day]
        buy = day_rows[day_rows["side"] == "BUY"]["qty"].sum()
        sell = day_rows[day_rows["side"] == "SELL"]["qty"].sum()
        assert buy == sell == 2000  # 4 buys + 4 sells of 500 each
