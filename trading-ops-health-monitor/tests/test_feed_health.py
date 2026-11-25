from ops.feed_health import check_feed, detect_sequence_gaps


def test_gaps_found():
    assert detect_sequence_gaps([1, 2, 4, 5]) == [3]


def test_gaps_none_when_continuous():
    assert detect_sequence_gaps([10, 11, 12]) == []


def test_gaps_empty_input():
    assert detect_sequence_gaps([]) == []


def test_healthy_feed_ok():
    result = check_feed({
        "name": "fx", "last_update_age_s": 1,
        "received_seqs": [1, 2, 3], "quotes_per_min": 100,
        "expected_quotes_per_min": 100,
    })
    assert result["status"] == "ok"
    assert result["stale"] is False


def test_stale_and_gaps_is_down():
    result = check_feed({
        "name": "fx", "last_update_age_s": 30,
        "received_seqs": [1, 3], "quotes_per_min": 100,
        "expected_quotes_per_min": 100,
    })
    assert result["status"] == "down"
    assert result["gaps"] == [2]


def test_rate_drop_is_degraded():
    result = check_feed({
        "name": "fx", "last_update_age_s": 1,
        "received_seqs": [1, 2, 3], "quotes_per_min": 50,
        "expected_quotes_per_min": 100,
    })
    assert result["status"] == "degraded"
    assert result["rate_ok"] is False
