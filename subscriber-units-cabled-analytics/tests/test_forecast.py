from uc_analytics import forecast, seed

DATA = seed.generate()


def test_forecast_120_length_and_horizon():
    series = forecast.daily_region_totals(DATA["actuals"], "Philadelphia")
    fc = forecast.forecast_120(series)
    assert len(fc) == 120
    assert fc[0][0] > series[-1][0]
    assert all(u > 0 for _d, u in fc)


def test_backtest_mape_is_small_and_measured():
    for region in seed.REGIONS:
        series = forecast.daily_region_totals(DATA["actuals"], region)
        bt = forecast.backtest(series)
        assert bt["origins"]
        assert 0 < bt["mean_mape_pct"] < 10  # seeded series is smooth


def test_forecast_rises_with_trend():
    series = forecast.daily_region_totals(DATA["actuals"], "Dacula")
    fc = forecast.forecast_120(series)
    first_week = sum(u for _d, u in fc[:7]) / 7
    last_week = sum(u for _d, u in fc[-7:]) / 7
    assert last_week > first_week  # seeded trend is upward
