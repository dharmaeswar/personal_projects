from uc_analytics import scorecard, seed

DATA = seed.generate()


def test_executive_summary_names_all_regions_and_events():
    text = scorecard.executive_summary(DATA)
    for region in seed.REGIONS:
        assert region in text
    for event in DATA["bulk_events"]:
        assert event["event_id"] in text
    assert "MAPE" in text


def test_variance_watchlist_filters_by_threshold():
    card = scorecard.national_scorecard(DATA["actuals"], DATA["forecasts"], "monthly")
    strict = scorecard.variance_watchlist(card, threshold_pct=0.5)
    loose = scorecard.variance_watchlist(card, threshold_pct=50.0)
    assert len(strict) >= len(loose) == 0
    assert all(abs(r["variance_pct"]) > 0.5 for r in strict)
