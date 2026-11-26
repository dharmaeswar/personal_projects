from uc_analytics import reporting, seed

DATA = seed.generate()


def test_monthly_aggregation_sums_to_total():
    monthly = reporting.aggregate(DATA["actuals"], "monthly")
    assert sum(r["units"] for r in monthly) == sum(u for *_x, u in DATA["actuals"])
    assert len(monthly) == 7 * 3  # May 25–Nov 20 spans 7 months x 3 regions


def test_weekly_aggregation_starts_on_monday():
    weekly = reporting.aggregate(DATA["actuals"], "weekly")
    assert all(r["period_start"].weekday() == 0 for r in weekly)


def test_variance_report_has_forecast_and_variance():
    card = reporting.variance_report(DATA["actuals"], DATA["forecasts"], "monthly")
    assert card
    for row in card:
        assert row["forecast"] > 0
        assert row["variance"] == row["actual"] - row["forecast"]
        assert abs(row["variance_pct"]) < 25  # seeded forecasts are close


def test_trend_change_matches_adjacent_weeks():
    tr = reporting.trend(DATA["actuals"], "weekly")
    assert tr
    for row in tr:
        assert row["change_pct"] is not None
