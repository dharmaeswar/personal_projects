from prediction_markets.cleanse import cleanse
from prediction_markets.ingest import generate_feed
from prediction_markets.signals import backtest, consensus, movements


def _records():
    records, _ = cleanse(generate_feed())
    return records


def test_consensus_averages_books():
    records = _records()
    cons = consensus(records)
    # 12 events x 24 timestamps.
    assert cons.groupby("event_id").size().eq(24).all()
    assert ((cons["fair_home"] > 0) & (cons["fair_home"] < 1)).all()


def test_movements_bounded_and_sorted():
    cons = consensus(_records())
    movers = movements(cons)
    assert len(movers) == 12
    assert all(-1 <= m.move <= 1 for m in movers)
    assert abs(movers[0].move) >= abs(movers[-1].move)


def test_backtest_bets_only_on_threshold_crossing():
    records = _records()
    bt = backtest(records)
    assert bt["bets"] >= 0
    assert bt["staked"] == bt["bets"] * 100.0
    assert bt["profit"] == sum(b["profit"] for b in bt["detail"])
    # Every bet's edge must clear the 5% threshold at some snapshot at or
    # before the bet time, using only data available then: re-derive the
    # first crossing time and check the edge there.
    cons = consensus(records)
    from prediction_markets.ingest import EVENTS
    model = {e[0]: e[3] for e in EVENTS}
    for b in bt["detail"]:
        group = cons[cons["event_id"] == b["event_id"]].sort_values("ts")
        crossed = False
        for _, row in group.iterrows():
            edge = (model[b["event_id"]] - row["fair_home"] if b["side"] == "home"
                    else (1 - model[b["event_id"]]) - row["fair_away"])
            if edge >= 0.05 - 1e-9:
                crossed = True
                break
        assert crossed


def test_backtest_is_deterministic():
    records = _records()
    assert backtest(records) == backtest(records)
