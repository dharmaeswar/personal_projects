from uc_analytics import impact, seed

DATA = seed.generate()


def test_activation_observed_close_to_stated_units():
    event = [e for e in DATA["bulk_events"] if e["event_id"] == "BULK-001"][0]
    res = impact.event_impact(DATA["actuals"], event)
    assert abs(res["unexplained"]) < 30  # trend/noise only; 118-unit step lands


def test_debulk_and_disconnection_are_negative():
    for eid in ("BULK-002", "BULK-003"):
        event = [e for e in DATA["bulk_events"] if e["event_id"] == eid][0]
        res = impact.event_impact(DATA["actuals"], event)
        assert res["observed_change"] < -30
        assert res["expected_change"] < 0


def test_all_events_have_windows():
    for event in DATA["bulk_events"]:
        res = impact.event_impact(DATA["actuals"], event)
        assert res["before_mean"] is not None and res["after_mean"] is not None
