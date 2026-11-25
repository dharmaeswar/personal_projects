from conftest import make_graph


def test_ground_returns_target_in_top_three():
    graph = make_graph()
    top = graph.ground("fix average off-by-one billing", top_k=3)
    ids = [n.node_id for n, _ in top]
    # The ticket itself ranks first (it contains the query words); the
    # target function must be grounded on the first try too.
    assert top[0][0].node_id == "ticket:SDLC-101"
    assert "fn:average" in ids


def test_ground_pulls_in_neighbours():
    graph = make_graph()
    ids = [n.node_id for n, _ in graph.ground("average total count", top_k=3)]
    assert "fn:average" in ids
    assert "file:billing.py" in ids  # one-hop neighbour of the matched function


def test_ground_empty_query_returns_nothing():
    assert make_graph().ground("the and for") == []


def test_first_try_hit_rate():
    graph = make_graph()
    queries = [
        ("fix average off-by-one", "fn:average"),
        ("test average totals", "test:test_average"),
    ]
    assert graph.first_try_hit_rate(queries) == 1.0


def test_first_try_hit_rate_miss():
    graph = make_graph()
    assert graph.first_try_hit_rate([("refund webhook retry", "fn:average")]) == 0.0


def test_edge_to_unknown_node_rejected():
    graph = make_graph()
    import pytest
    with pytest.raises(ValueError):
        graph.add_edge("fn:average", "fn:missing", "calls")
