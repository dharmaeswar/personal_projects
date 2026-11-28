import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fin_impact import data, sql_analysis  # noqa: E402


def _conn():
    conn = sql_analysis.connect()
    sql_analysis.load(conn, data.make_conversations(n_per_customer=100,
                                                    seed=1))
    return conn


def test_make_conversations_counts():
    convs = data.make_conversations(n_per_customer=100, seed=1)
    assert len(convs) == 500
    assert {c.period for c in convs} == {"before", "after"}


def test_no_fin_resolutions_before_deployment():
    convs = data.make_conversations(n_per_customer=50, seed=2)
    assert all(not c.resolved_by_fin for c in convs
               if c.period == "before")


def test_metrics_after_beats_before():
    conn = _conn()
    m = sql_analysis.metrics(conn)
    assert m["after"]["resolution_rate"] > m["before"]["resolution_rate"]
    assert m["after"]["mean_handle_minutes"] < m["before"]["mean_handle_minutes"]
    assert m["after"]["escalation_rate"] < m["before"]["escalation_rate"]


def test_metrics_per_customer():
    conn = _conn()
    m = sql_analysis.metrics(conn, "acme")
    assert m["after"]["conversations"] > 0
    assert m["before"]["conversations"] > 0


def test_by_channel_covers_all_channels():
    conn = _conn()
    rows = sql_analysis.by_channel(conn)
    assert {r["channel"] for r in rows} == set(data.CHANNELS)
    assert all(0.0 <= r["resolution_rate"] <= 1.0 for r in rows)
