import math
from datetime import datetime, timezone

import pytest

from prediction_markets.ingest import (
    EVENTS, Snapshot, american_to_prob, generate_feed, prob_to_american,
)


def test_american_to_prob_positive():
    assert american_to_prob(100) == pytest.approx(0.5)
    assert american_to_prob(200) == pytest.approx(1 / 3)


def test_american_to_prob_negative():
    assert american_to_prob(-100) == pytest.approx(0.5)
    assert american_to_prob(-200) == pytest.approx(2 / 3)


def test_prob_round_trip():
    for p in (0.2, 0.35, 0.5, 0.65, 0.8):
        assert american_to_prob(prob_to_american(p)) == pytest.approx(p, abs=0.01)


def test_feed_is_deterministic():
    a = generate_feed(seed=7)
    b = generate_feed(seed=7)
    assert [(s.event_id, s.book, s.ts, s.odds_home) for s in a] == \
           [(s.event_id, s.book, s.ts, s.odds_home) for s in b]


def test_feed_shape_and_defects():
    feed = generate_feed()
    # 12 events x 24 snapshots x 3 books = 864, plus 2 appended duplicates.
    assert len(feed) == 866
    assert len({e[0] for e in EVENTS}) == 12
    missing = [s for s in feed if s.odds_home is None or s.odds_away is None]
    assert len(missing) == 2


def test_feed_covers_all_books_and_events():
    feed = generate_feed()
    assert {s.book for s in feed} == {"BookA", "BookB", "BookC"}
    assert {s.event_id for s in feed} == {e[0] for e in EVENTS}
