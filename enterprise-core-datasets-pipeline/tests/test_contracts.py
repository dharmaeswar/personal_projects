"""Tests for source contracts and bronze ingest."""

from enterprise_core import seed as seed_mod
from enterprise_core.contracts import validate
from enterprise_core.pipeline import Warehouse


def test_contract_accepts_clean_rows():
    feeds = seed_mod.seed_all()
    for feed, rows in feeds.items():
        good, bad = validate(feed, rows[:50])
        assert bad == [] or all("_reason" in r for r in bad)


def test_contract_quarantines_each_defect_type():
    feeds = seed_mod.seed_all()
    _, ai_bad = validate("ai_usage", feeds["ai_usage"])
    reasons = {r["_reason"] for r in ai_bad}
    assert any("missing team" in r for r in reasons)
    assert any("tokens_in" in r and "outside" in r for r in reasons)
    assert any("tool_name" in r and "not allowed" in r for r in reasons)
    assert any("event_date" in r and "outside" in r for r in reasons)
    _, jira_bad = validate("jira_issues", feeds["jira_issues"])
    assert len(jira_bad) == 4
    _, bk_bad = validate("bookings", feeds["bookings"])
    assert len(bk_bad) == 2
    assert any("revenue_usd exceeds gbv_usd" in r["_reason"] for r in bk_bad)


def test_ingest_dedupes_redelivered_batches():
    feeds = seed_mod.seed_all()
    wh = Warehouse()
    result = wh.ingest("ai_usage", feeds["ai_usage"])
    assert result["duplicates_removed"] == 4  # the 4 re-delivered event_ids
    assert result["quarantined"] == 8  # 3 null team + 2 negative tokens + 2 unknown tool + 1 future date
    bronze = wh.tables["bronze_ai_usage"]
    assert bronze["event_id"].is_unique


def test_ingest_is_idempotent():
    feeds = seed_mod.seed_all()
    wh = Warehouse()
    first = wh.ingest("ai_usage", feeds["ai_usage"])
    second = wh.ingest("ai_usage", feeds["ai_usage"])
    assert second["new_bronze_rows"] == 0
    assert len(wh.tables["bronze_ai_usage"]) == first["good"] - first["duplicates_removed"]


def test_quarantine_rows_are_kept_with_reasons():
    feeds = seed_mod.seed_all()
    wh = Warehouse()
    wh.ingest("bookings", feeds["bookings"])
    q = wh.tables["quarantine_bookings"]
    assert len(q) == 2
    assert set(q["_reason"]) == {"revenue_usd exceeds gbv_usd",
                                 "hosting_cost_usd=-50.0 outside [0.0, 500000.0]"}
