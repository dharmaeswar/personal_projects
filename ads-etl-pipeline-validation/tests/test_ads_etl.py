"""Tests for the advertising ETL pipeline validation project."""

from __future__ import annotations

import sqlite3

import pytest

from ads_etl.checks import (
    check_clicks_within_impressions,
    check_completeness,
    check_late_arriving,
    check_ranges,
    check_reconciliation,
    check_referential_integrity,
    check_spend_arithmetic,
    check_uniqueness,
    run_all_checks,
)
from ads_etl.data import (
    PLANTED_VIOLATIONS,
    WATERMARK_TS,
    generate_ads,
    generate_all,
    generate_campaigns,
    generate_events,
)
from ads_etl.monitoring import PipelineMetrics
from ads_etl.pipeline import (
    append_log,
    build_gold,
    build_silver,
    connect,
    load_bronze,
    read_log,
    read_table,
)
from ads_etl.report import render_report
from ads_etl.schema import (
    ADS_SCHEMA,
    CAMPAIGNS_SCHEMA,
    EVENTS_SCHEMA,
    GOLD_SCHEMA,
    SILVER_SCHEMA,
    enforce_schema,
)
from ads_etl.streaming import EventConsumer, consume_all_in_batches


@pytest.fixture(scope="module")
def data():
    return generate_all()


@pytest.fixture(scope="module")
def bronze(data):
    return data["events"]


@pytest.fixture(scope="module")
def silver_quarantine(data):
    return build_silver_in_memory(data)


def build_silver_in_memory(data):
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "test.db")
        load_bronze(conn, data["campaigns"], data["ads"], data["events"])
        result = build_silver(conn, data["events"], data["ads"], data["campaigns"])
        conn.close()
        return result


@pytest.fixture(scope="module")
def gold(silver_quarantine, data):
    import tempfile
    from pathlib import Path

    silver, _, _ = silver_quarantine
    with tempfile.TemporaryDirectory() as tmp:
        conn = connect(Path(tmp) / "test.db")
        load_bronze(conn, data["campaigns"], data["ads"], data["events"])
        build_silver(conn, data["events"], data["ads"], data["campaigns"])
        gold_rows, lineage = build_gold(conn, silver)
        conn.close()
        return gold_rows, lineage


def test_generate_shapes(data, bronze):
    assert len(data["campaigns"]) == 12
    assert len(data["ads"]) == 30
    assert len(data["clean_events"]) == 240
    assert len(data["planted_bad_rows"]) == 14
    assert len(bronze) == 254
    assert sum(PLANTED_VIOLATIONS.values()) == 14


def test_clean_events_pass_schema(data):
    assert enforce_schema(data["clean_events"], EVENTS_SCHEMA, "events") == []
    assert enforce_schema(data["campaigns"], CAMPAIGNS_SCHEMA, "campaigns") == []
    assert enforce_schema(data["ads"], ADS_SCHEMA, "ads") == []


def test_schema_missing_column(data):
    rows = [dict(r) for r in data["campaigns"]]
    del rows[0]["channel"]
    problems = enforce_schema(rows, CAMPAIGNS_SCHEMA, "campaigns")
    assert any("missing column: channel" in p.problem for p in problems)


def test_schema_unexpected_column(data):
    rows = [dict(r) for r in data["ads"]]
    rows[0]["surprise"] = 1
    problems = enforce_schema(rows, ADS_SCHEMA, "ads")
    assert any("unexpected column: surprise" in p.problem for p in problems)


def test_schema_null_in_non_nullable(bronze):
    rows = [dict(r) for r in bronze]
    rows[0]["event_id"] = None
    problems = enforce_schema(rows, EVENTS_SCHEMA, "events")
    assert any("nulls in non-nullable column event_id" in p.problem for p in problems)


def test_completeness_flags_null_campaigns(bronze):
    result = check_completeness(bronze, ["event_id", "ad_id", "campaign_id", "event_ts"])
    assert not result.passed
    assert "campaign_id: 3 nulls" in result.detail
    assert len(result.failing_rows) == 3


def test_uniqueness_flags_duplicate_event_ids(bronze):
    result = check_uniqueness(bronze, "event_id")
    assert not result.passed
    assert len(result.failing_rows) == 3
    assert "3 duplicated event_id values" in result.detail


def test_ranges_flag_negative_spend(bronze):
    result = check_ranges(bronze, "spend_usd", low=0)
    assert not result.passed
    assert len(result.failing_rows) == 2


def test_clicks_within_impressions_flags_two(bronze):
    result = check_clicks_within_impressions(bronze)
    assert not result.passed
    assert len(result.failing_rows) == 2


def test_ranges_flag_future_event_ts(bronze):
    result = check_ranges(bronze, "event_ts", low="2026-09-01T00:00:00", high="2026-11-16T23:59:59")
    assert not result.passed
    assert len(result.failing_rows) == 1


def test_fk_flags_unknown_ads(bronze, data):
    result = check_referential_integrity(bronze, "ad_id", data["ads"], "ad_id")
    assert not result.passed
    assert len(result.failing_rows) == 2


def test_fk_ignores_null_campaign_ids(bronze, data):
    # Null campaign ids are a completeness problem, not a foreign-key problem.
    result = check_referential_integrity(bronze, "campaign_id", data["campaigns"], "campaign_id")
    assert result.passed


def test_spend_arithmetic_flags_three(bronze):
    # 1 wrong spend + 2 negative-spend rows (spend -5 vs expected 0).
    result = check_spend_arithmetic(bronze)
    assert not result.passed
    assert len(result.failing_rows) == 3


def test_bronze_check_suite_finds_seven_failures(bronze, data):
    results = run_all_checks(bronze, data["ads"], data["campaigns"])
    assert len(results) == 10
    failed = [r for r in results if not r.passed]
    assert len(failed) == 7
    assert {r.name for r in failed} == {
        "completeness",
        "uniqueness:event_id",
        "range:spend_usd",
        "clicks_within_impressions",
        "range:event_ts",
        "fk:ad_id->ad_id",
        "spend_arithmetic",
    }


def test_late_arriving_rows_are_counted_not_failed(bronze):
    result = check_late_arriving(bronze)
    assert result.passed
    assert len(result.failing_rows) == 2
    assert "2 late-arriving rows" in result.detail


def test_silver_quarantine_counts(silver_quarantine):
    silver, quarantine, _ = silver_quarantine
    assert len(silver) == 240
    assert len(quarantine) == 14
    assert len(silver) + len(quarantine) == 254


def test_quarantine_reasons_cover_every_violation_type(silver_quarantine):
    _, quarantine, _ = silver_quarantine
    reasons = " | ".join(q["quarantine_reason"] for q in quarantine)
    for label in (
        "duplicate event_id",
        "null key",
        "spend out of range",
        "clicks exceed impressions",
        "unknown ad_id",
        "event_ts out of range",
        "wrong spend",
    ):
        assert label in reasons


def test_silver_passes_every_check(silver_quarantine, data):
    silver, _, _ = silver_quarantine
    results = run_all_checks(silver, data["ads"], data["campaigns"])
    assert all(r.passed for r in results), [str(r) for r in results]
    assert enforce_schema(silver, SILVER_SCHEMA, "events_silver") == []


def test_late_rows_land_in_silver_flagged(silver_quarantine):
    silver, _, _ = silver_quarantine
    late = [r for r in silver if r["late_arriving"] == 1]
    assert len(late) == 2
    assert all(r["event_ts"] < WATERMARK_TS for r in late)


def test_silver_lineage_covers_every_row(silver_quarantine, bronze):
    silver, _, lineage = silver_quarantine
    assert len(lineage) == len(silver) == 240
    assert {l["silver_event_id"] for l in lineage} == {r["event_id"] for r in silver}
    assert all(l["source_table"] == "events_bronze" for l in lineage)


def test_gold_reconciles_with_silver(silver_quarantine, gold):
    silver, _, _ = silver_quarantine
    gold_rows, _ = gold
    result = check_reconciliation(silver, gold_rows)
    assert result.passed
    assert enforce_schema(gold_rows, GOLD_SCHEMA, "gold_daily_spend") == []
    assert round(sum(g["spend_usd"] for g in gold_rows), 2) == round(
        sum(r["spend_usd"] for r in silver), 2
    )


def test_gold_lineage_sums_to_silver(silver_quarantine, gold):
    silver, _, _ = silver_quarantine
    gold_rows, lineage = gold
    assert len(lineage) == len(gold_rows)
    assert sum(entry["source_row_count"] for entry in lineage) == len(silver)
    seen = [eid for entry in lineage for eid in entry["source_event_ids"]]
    assert len(seen) == len(set(seen)) == len(silver)


def test_gold_channel_matches_campaign(data, gold):
    gold_rows, _ = gold
    channel_of = {c["campaign_id"]: c["channel"] for c in data["campaigns"]}
    assert all(g["channel"] == channel_of[g["campaign_id"]] for g in gold_rows)


def test_sqlite_tables_round_trip(data, tmp_path):
    db_path = tmp_path / "roundtrip.db"
    conn = connect(db_path)
    load_bronze(conn, data["campaigns"], data["ads"], data["events"])
    assert len(read_table(conn, "events_bronze")) == 254
    silver, quarantine, _ = build_silver(conn, data["events"], data["ads"], data["campaigns"])
    assert len(read_table(conn, "events_silver")) == 240
    assert len(read_table(conn, "quarantine")) == 14
    gold_rows, _ = build_gold(conn, silver)
    assert len(read_table(conn, "gold_daily_spend")) == len(gold_rows)
    # The gold table in SQLite matches the SQL-built gold rows exactly.
    db_gold = read_table(conn, "gold_daily_spend")
    assert db_gold == gold_rows
    conn.close()


def test_transaction_log_versions_increment(tmp_path):
    log_path = tmp_path / "pipeline_log.json"
    first = append_log(log_path, "events_bronze", "test write", 5, 0)
    second = append_log(log_path, "events_silver", "test rewrite", 4, 1)
    assert first["version"] == 1
    assert second["version"] == 2
    assert second["rows_added"] == 4
    assert second["rows_removed"] == 1
    assert len(read_log(log_path)) == 2


def test_consumer_delivers_in_order_and_commits(bronze):
    consumer = EventConsumer()
    consumer.produce(bronze[:150])
    consumer.produce(bronze[150:])
    assert consumer.size == 254
    first = consumer.poll(100)
    assert [r.offset for r in first] == list(range(100))
    assert consumer.pending == 254  # poll does not commit
    consumer.commit(first)
    assert consumer.pending == 154
    rest = consume_all_in_batches(consumer, batch_size=100)
    assert len(rest) == 154
    assert consumer.pending == 0
    assert consumer.committed_offset == 254


def test_consumer_replays_uncommitted_batch(bronze):
    consumer = EventConsumer()
    consumer.produce(bronze[:10])
    batch = consumer.poll(10)
    assert len(batch) == 10
    replay = consumer.poll(10)  # nothing committed: same records again
    assert [r.offset for r in replay] == [r.offset for r in batch]
    consumer.commit(batch)
    assert consumer.poll(10) == []


def test_monitoring_failure_and_late_rates():
    metrics = PipelineMetrics(
        bronze_rows=254, silver_rows=240, quarantine_rows=14, late_rows=2, gold_groups=100
    )
    assert metrics.failure_rate == pytest.approx(14 / 254)
    assert metrics.late_rate == pytest.approx(2 / 240)
    text = "\n".join(metrics.summary_lines())
    assert "failure rate: 5.51%" in text
    assert "late-arrival rate: 0.83%" in text


def test_report_lists_failures_and_counts(bronze, data, silver_quarantine, gold):
    silver, quarantine, _ = silver_quarantine
    gold_rows, _ = gold
    results = run_all_checks(bronze, data["ads"], data["campaigns"])
    reconciliation = check_reconciliation(silver, gold_rows)
    metrics = PipelineMetrics(
        bronze_rows=254, silver_rows=240, quarantine_rows=14, late_rows=2,
        gold_groups=len(gold_rows),
    )
    report = render_report(
        results,
        bronze_rows=254,
        silver_rows=len(silver),
        quarantine_rows=len(quarantine),
        late_rows=2,
        gold_groups=len(gold_rows),
        reconciliation=reconciliation,
        metrics=metrics,
        silver_spend=round(sum(r["spend_usd"] for r in silver), 2),
        gold_spend=round(sum(g["spend_usd"] for g in gold_rows), 2),
    )
    assert "Bronze events: 254 rows" in report
    assert "Quarantined rows: 14 rows" in report
    assert "3 of 10 bronze checks" in report or "7 FAILED" in report
    assert "gold matches silver on all" in report
    assert "failure rate: 5.51%" in report
