from sdlc_agents import observability


def test_dashboard_rollup(tmp_path):
    conn = observability.init_db(str(tmp_path / "test.sqlite"))
    observability.record_run(conn, observability.RunRecord("T1", "codegen", True, "ok", []))
    observability.record_run(conn, observability.RunRecord("T1", "review", False, "blocked", ["BLOCK x"]))
    observability.record_run(conn, observability.RunRecord("T1", "release", False, "blocked", []))
    observability.record_spend(conn, "T1", "sdlc-strong", "codegen", 2.40)
    d = observability.dashboard(conn)
    assert d["total_stage_runs"] == 3
    assert d["overall_pass_rate"] == 0.333
    assert d["pass_rate_by_stage"]["codegen"]["pass_rate"] == 1.0
    assert d["total_model_spend_usd"] == 2.40
    assert d["governance"]["blocked_releases"] == 1
    assert d["governance"]["unreviewed_auto_merges"] == 0
    md = observability.dashboard_markdown(conn)
    assert "Blocked releases: 1" in md
    conn.close()


def test_empty_dashboard():
    import sqlite3
    conn = observability.init_db(":memory:")
    d = observability.dashboard(conn)
    assert d["total_stage_runs"] == 0
    assert d["overall_pass_rate"] == 0.0
    conn.close()
