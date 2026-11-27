import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client_analytics import analysis, dashboard, data, ingest, report, validate


def _valid(tmp_path):
    conn = ingest.open_db(str(tmp_path / "test.db"))
    ingest.load(conn, data.generate())
    valid, _ = validate.validate_transactions(conn)
    return conn, valid


def test_monthly_kpis_cover_six_months(tmp_path):
    conn, valid = _valid(tmp_path)
    monthly = analysis.kpi_by_month(valid)
    assert [r["month"] for r in monthly] == [
        "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    for r in monthly:
        assert r["txn_count"] > 0
        assert r["volume"] > 0
        assert abs(r["avg_ticket"] - r["volume"] / r["txn_count"]) < 0.01
        assert r["active_accounts"] > 0


def test_month_over_month_first_is_none(tmp_path):
    conn, valid = _valid(tmp_path)
    monthly = analysis.month_over_month(analysis.kpi_by_month(valid))
    assert monthly[0]["volume_change_pct"] is None
    assert all(isinstance(r["volume_change_pct"], float) for r in monthly[1:])


def test_channel_totals_add_up(tmp_path):
    conn, valid = _valid(tmp_path)
    monthly = analysis.kpi_by_month(valid)
    channels = analysis.kpi_by_channel(valid)
    assert abs(sum(c["volume"] for c in channels)
               - sum(m["volume"] for m in monthly)) < 0.01
    assert sum(c["txn_count"] for c in channels) == sum(
        m["txn_count"] for m in monthly)
    assert {c["channel"] for c in channels} <= {"Online", "Branch", "Mobile", "Phone"}


def test_top_clients_sorted_and_capped(tmp_path):
    conn, valid = _valid(tmp_path)
    top = analysis.top_clients(conn, valid)
    assert len(top) == 10
    volumes = [t["volume"] for t in top]
    assert volumes == sorted(volumes, reverse=True)
    assert all(t["segment"] in ("Retail", "Small Business", "Wealth") for t in top)


def test_ops_summary_counts(tmp_path):
    conn, valid = _valid(tmp_path)
    ops = analysis.ops_summary(conn)
    assert sum(o["count"] for o in ops) == 120
    assert all(o["avg_resolution_days"] > 0 for o in ops)


def test_dashboard_writes_files(tmp_path):
    conn, valid = _valid(tmp_path)
    monthly = analysis.month_over_month(analysis.kpi_by_month(valid))
    channels = analysis.kpi_by_channel(valid)
    top = analysis.top_clients(conn, valid)
    ops = analysis.ops_summary(conn)
    _, exceptions = validate.validate_transactions(conn)
    files = dashboard.build(str(tmp_path / "out"), monthly, channels, top,
                            ops, exceptions, [])
    for name in ("kpi_by_month.csv", "kpi_by_channel.csv", "top_clients.csv",
                 "ops_summary.csv", "exceptions.csv", "dashboard.html"):
        assert name in files
        assert os.path.getsize(os.path.join(str(tmp_path / "out"), name)) > 0
    html_text = open(os.path.join(str(tmp_path / "out"), "dashboard.html")).read()
    assert "2026-05" in html_text
    assert "Exceptions" in html_text


def test_report_mentions_totals(tmp_path):
    conn, valid = _valid(tmp_path)
    monthly = analysis.month_over_month(analysis.kpi_by_month(valid))
    channels = analysis.kpi_by_channel(valid)
    top = analysis.top_clients(conn, valid)
    ops = analysis.ops_summary(conn)
    _, exceptions = validate.validate_transactions(conn)
    text = report.build(monthly, channels, top, ops, len(valid), 601,
                        exceptions, [])
    assert "Transactions processed: 601" in text
    assert "Total valid volume" in text
    assert "Monthly trend" in text
