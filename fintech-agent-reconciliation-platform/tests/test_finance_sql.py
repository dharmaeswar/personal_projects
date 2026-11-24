from fintech_agents.finance_sql import FinanceWarehouse


def _warehouse():
    return FinanceWarehouse(
        revenue=[("2026-09", "subscriptions", 800_000),
                 ("2026-09", "services", 200_000),
                 ("2026-10", "subscriptions", 900_000),
                 ("2026-10", "services", 250_000),
                 ("2026-11", "subscriptions", 1_000_000),
                 ("2026-11", "services", 300_000)],
        billings=[("INV-1", "2026-11", "subscriptions", 1_100_000,
                   1_000_000),
                  ("INV-2", "2026-11", "services", 300_000, 300_000)],
        close_tasks=[("t1", "2026-11", "done"),
                     ("t2", "2026-11", "done"),
                     ("t3", "2026-11", "pending")])


def test_monthly_running_total():
    rows = _warehouse().monthly_running_total()
    assert [(r["month"], r["month_total_minor"],
             r["running_total_minor"]) for r in rows] == [
        ("2026-09", 1_000_000, 1_000_000),
        ("2026-10", 1_150_000, 2_150_000),
        ("2026-11", 1_300_000, 3_450_000),
    ]


def test_yoy_growth_first_month_has_no_prior():
    rows = _warehouse().yoy_growth()
    assert rows[0]["prior_month_total_minor"] is None
    assert rows[0]["growth_pct"] is None
    assert rows[1]["growth_pct"] == 15.0
    assert rows[2]["growth_pct"] == 13.04


def test_segment_rank_orders_by_total():
    rows = _warehouse().segment_rank()
    assert rows[0]["segment"] == "subscriptions"
    assert rows[0]["revenue_rank"] == 1
    assert rows[0]["total_minor"] == 2_700_000
    assert rows[1]["segment"] == "services"
    assert rows[1]["revenue_rank"] == 2


def test_unrecognised_billings_only_partial():
    rows = _warehouse().unrecognised_billings()
    assert len(rows) == 1
    assert rows[0]["invoice_id"] == "INV-1"
    assert rows[0]["unrecognised_minor"] == 100_000


def test_close_status_pct_done():
    rows = _warehouse().close_status()
    assert rows[0]["tasks"] == 3
    assert rows[0]["tasks_done"] == 2
    assert rows[0]["pct_done"] == 66.7
