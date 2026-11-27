"""Tests for the dbt-style modeling layer (Discord update): squad sources,
model builds, schema tests, freshness, and the semantic layer."""
import sqlite3

import pytest

from product_analytics import db, ingest, models, seed, transforms


def _seeded_conn():
    conn = db.connect()
    events = seed.generate_events(count=6000)
    ingest.load_raw(conn, events)
    ingest.build_staging(conn)
    return conn


def test_schema_loads_in_dependency_order():
    schema = models.load_schema()
    names = [m["name"] for m in schema["models"]]
    assert names == [
        "stg_events", "stg_game_catalog", "stg_ads",
        "int_user_game_sessions", "int_ads_daily",
        "mart_gaming_daily", "mart_ads_measurement_daily",
    ]
    # Every ref points at a model listed earlier in the file.
    built = set()
    for name in names:
        sql = models.find_model_sql(name)
        for ref in models.REF_RE.findall(sql):
            assert ref in built, f"{name} refs {ref} before it is built"
        built.add(name)


def test_seed_squad_sources_is_deterministic():
    conn = _seeded_conn()
    first = models.seed_squad_sources(conn)
    second = models.seed_squad_sources(conn)
    assert first == second
    assert first["games"] == 8
    assert first["ads_rows"] == 56  # 8 campaign/channel combos x 7 days
    assert first["sessions"] > 400
    assert conn.execute("SELECT COUNT(*) FROM game_catalog_raw").fetchone()[0] == 8


def test_build_models_creates_marts_and_passes_tests(tmp_path):
    conn = _seeded_conn()
    out = models.build_models(conn)
    assert out["row_counts"]["mart_gaming_daily"] > 0
    assert out["row_counts"]["mart_ads_measurement_daily"] == 56
    assert all(r["status"] == "pass" for r in out["tests"])
    assert all(s["status"] == "pass" for s in out["semantic"])
    # Freshness check is part of the test list.
    assert any(r["test"].startswith("freshness") for r in out["tests"])
    # Results persisted for the docs/catalog.
    stored = conn.execute("SELECT COUNT(*) FROM model_test_results").fetchone()[0]
    assert stored == len(out["tests"])


def test_gaming_mart_grain_and_math():
    conn = _seeded_conn()
    models.build_models(conn)
    dupes = conn.execute(
        "SELECT COUNT(*) FROM (SELECT metric_date, game_id FROM mart_gaming_daily "
        "GROUP BY metric_date, game_id HAVING COUNT(*) > 1)"
    ).fetchone()[0]
    assert dupes == 0
    # Play minutes recomputed from sessions agree with the mart.
    row = conn.execute(
        "SELECT SUM(duration_sec) / 60.0 FROM int_user_game_sessions"
    ).fetchone()[0]
    mart_total = conn.execute("SELECT SUM(play_minutes) FROM mart_gaming_daily").fetchone()[0]
    assert mart_total == pytest.approx(row)
    # Every mart game exists in the catalog (user-to-game signal is joined, not dangling).
    dangling = conn.execute(
        "SELECT COUNT(*) FROM mart_gaming_daily m LEFT JOIN stg_game_catalog c "
        "ON c.game_id = m.game_id WHERE c.game_id IS NULL"
    ).fetchone()[0]
    assert dangling == 0


def test_ads_mart_ctr_and_cpc_math():
    conn = _seeded_conn()
    models.build_models(conn)
    row = conn.execute(
        "SELECT clicks, impressions, spend_usd, ctr, cpc "
        "FROM mart_ads_measurement_daily WHERE clicks > 0 LIMIT 1"
    ).fetchone()
    clicks, impressions, spend, ctr, cpc = row
    assert ctr == pytest.approx(clicks / impressions)
    assert cpc == pytest.approx(spend / clicks)
    assert conn.execute(
        "SELECT COUNT(*) FROM mart_ads_measurement_daily WHERE ctr < 0 OR ctr > 1"
    ).fetchone()[0] == 0


def test_schema_test_catches_bad_data():
    conn = _seeded_conn()
    models.build_models(conn)
    # A negative spend row breaks the non_negative test on the ads mart.
    conn.execute(
        "INSERT INTO mart_ads_measurement_daily "
        "(metric_date, campaign_id, campaign_name, channel, impressions, clicks, "
        " spend_usd, ctr, cpc) VALUES ('2026-11-14','cmp_bad','Bad','video',10,1,-5.0,0.1,1.0)"
    )
    schema = models.load_schema()
    results = models.run_schema_tests(conn, schema)
    bad = [r for r in results
           if r["model"] == "mart_ads_measurement_daily"
           and r["test"] == "mart_ads_measurement_daily.non_negative(spend_usd)"]
    assert bad and bad[0]["status"] == "fail"


def test_relationship_test_catches_unknown_game():
    conn = _seeded_conn()
    models.build_models(conn)
    conn.execute(
        "INSERT INTO int_user_game_sessions (session_id, user_id, game_id, title, "
        "genre, platform, session_date, duration_sec, event_count) "
        "VALUES ('s99999','u0001','g999','Unknown','Action','PC','2026-11-14',600,10)"
    )
    schema = models.load_schema()
    results = models.run_schema_tests(conn, schema)
    rel = [r for r in results
           if r["model"] == "int_user_game_sessions" and "relationships" in r["test"]]
    assert rel and rel[0]["status"] == "fail"


def test_semantic_layer_metrics_resolve():
    conn = _seeded_conn()
    models.build_models(conn)
    layer = models.load_semantic_layer()
    assert "gaming_dau" in layer["metrics"]
    assert "ads_ctr" in layer["metrics"]
    for name, meta in layer["metrics"].items():
        value = conn.execute(
            f"SELECT {meta['sql']} FROM {meta['model']} LIMIT 1"
        ).fetchone()[0]
        assert value is not None, f"metric {name} evaluates to NULL on the mart"


def test_freshness_fails_on_stale_data():
    conn = _seeded_conn()
    models.build_models(conn)
    schema = models.load_schema()
    assert models.check_freshness(conn, schema, "2026-11-14")["status"] == "pass"
    assert models.check_freshness(conn, schema, "2026-11-20")["status"] == "fail"


def test_unresolved_ref_raises():
    with pytest.raises(ValueError):
        models.resolve_refs("SELECT * FROM {{ ref('no_such_model') }}", set())
