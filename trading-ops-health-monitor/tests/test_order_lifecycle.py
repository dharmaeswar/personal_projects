from ops.order_lifecycle import check_orders


def _orders():
    return [
        {"order_id": "O1", "symbol": "AAPL", "status": "acked", "last_update_s": 100},
        {"order_id": "O2", "symbol": "MSFT", "status": "filled", "last_update_s": 95},
        {"order_id": "O3", "symbol": "AAPL", "status": "new", "last_update_s": 40},
        {"order_id": "O4", "symbol": "MSFT", "status": "rejected", "last_update_s": 120},
    ]


def test_stuck_and_unacked_flagged():
    result = check_orders(_orders(), now_s=130)
    assert result["stuck"] == ["O3"]
    assert result["unacked"] == ["O3"]


def test_reject_rate_computed():
    result = check_orders(_orders(), now_s=130)
    assert result["reject_rate"] == 0.25
    assert result["reject_breach"] is True


def test_exceptions_grouped_by_symbol():
    result = check_orders(_orders(), now_s=130)
    assert result["exceptions_by_symbol"]["AAPL"] == 2
    assert result["exceptions_by_symbol"]["MSFT"] == 1


def test_clean_book_no_exceptions():
    clean = [{"order_id": "O9", "symbol": "AAPL", "status": "filled", "last_update_s": 129}]
    result = check_orders(clean, now_s=130)
    assert result["stuck"] == []
    assert result["reject_rate"] == 0.0
    assert result["reject_breach"] is False
