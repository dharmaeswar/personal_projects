from datetime import date

from uc_analytics import seed


def test_generate_is_deterministic():
    a = seed.generate()
    b = seed.generate()
    assert a == b


def test_actuals_cover_all_communities_and_days():
    data = seed.generate()
    assert len(data["actuals"]) == 180 * 11  # 180 days x 11 communities
    days = {d for d, _r, _c, _u in data["actuals"]}
    assert len(days) == 180
    assert min(days) == date(2026, 5, 25)
    assert max(days) == date(2026, 11, 20)


def test_billing_feed_drops_dac203_for_a_week():
    data = seed.generate()
    missing = [(d, c) for d, _r, c, _u in data["actuals"]
               if c == "DAC-203" and date(2026, 8, 3) <= d <= date(2026, 8, 9)]
    billed = {(d, c) for d, _r, c, _u in data["billing"]}
    assert missing and all((d, c) not in billed for d, c in missing)


def test_bulk_activation_lands_in_actuals():
    data = seed.generate()
    by_day = {(d, c): u for d, _r, c, u in data["actuals"]}
    before = [by_day[(date(2026, 9, d), "PHL-102")] for d in range(7, 14)]
    after = [by_day[(date(2026, 9, d), "PHL-102")] for d in range(14, 21)]
    assert sum(after) / len(after) - sum(before) / len(before) > 80


def test_forecast_snapshots_cover_120_days():
    data = seed.generate()
    snap = sorted({s for s, _t, _r, _u in data["forecasts"]})
    assert len(snap) == 12
    first = [f for f in data["forecasts"] if f[0] == snap[0]]
    assert len(first) == 120 * 3  # 120 days x 3 regions
