"""Tests for dimensions (SCD2), facts, and incremental loads."""

from enterprise_core import seed as seed_mod
from enterprise_core.pipeline import Warehouse


def _loaded_wh():
    wh = Warehouse()
    feeds = seed_mod.seed_all()
    for feed in ("ai_usage", "jira_issues", "bookings"):
        wh.ingest(feed, feeds[feed])
    wh.build_dims()
    wh.build_facts()
    return wh


def test_dim_tool_scd2_price_change():
    wh = _loaded_wh()
    dim = wh.tables["dim_tool"]
    copilot = dim[dim["tool_name"] == "copilot-pro"].sort_values("effective_from")
    assert len(copilot) == 2
    assert list(copilot["price_per_1k_tokens"]) == [3.00, 2.50]
    assert list(copilot["is_current"]) == [0, 1]
    assert copilot.iloc[0]["effective_to"] == "2026-10-31"
    # exactly one current row per tool
    current = dim[dim["is_current"] == 1]
    assert len(current) == 4
    assert current.groupby("tool_name").size().eq(1).all()


def test_dim_team_covers_both_feeds():
    wh = _loaded_wh()
    teams = set(wh.tables["dim_team"]["team"])
    assert teams == {"platform", "payments", "trust", "growth", "finance"}


def test_fact_ai_usage_daily_ties_to_bronze():
    wh = _loaded_wh()
    fact = wh.tables["fact_ai_usage_daily"]
    bronze = wh.tables["bronze_ai_usage"]
    assert abs(fact["cost_usd"].sum() - bronze["cost_usd"].sum()) < 0.01
    assert fact["events"].sum() == len(bronze)
    assert fact.duplicated(["date", "tool_name", "team"]).sum() == 0
    # point-in-time price: copilot-pro rows before Nov 1 carry 3.00
    oct_rows = fact[(fact["tool_name"] == "copilot-pro") & (fact["date"] < "2026-11-01")]
    assert (oct_rows["price_per_1k_tokens"] == 3.00).all()
    nov_rows = fact[(fact["tool_name"] == "copilot-pro") & (fact["date"] >= "2026-11-01")]
    assert (nov_rows["price_per_1k_tokens"] == 2.50).all()


def test_fact_unit_economics_margin_arithmetic():
    wh = _loaded_wh()
    ue = wh.tables["fact_unit_economics_daily"]
    assert len(ue) == 56  # one row per day
    assert ((ue["margin_usd"] - (ue["revenue_usd"] - ue["total_cost_usd"])).abs() < 0.01).all()
    assert ((ue["revenue_usd"] <= ue["gbv_usd"])).all()
    costs = wh.tables["fact_cost_daily"]
    assert len(costs) == 56 * 3  # three cost categories per day
    assert abs(costs.groupby("date")["amount_usd"].sum().sum()
               - ue["total_cost_usd"].sum()) < 0.01


def test_fact_jira_weekly_snapshot():
    wh = _loaded_wh()
    weekly = wh.tables["fact_jira_weekly"]
    assert not weekly.empty
    assert weekly["open_issues"].sum() > 0
    assert weekly.duplicated(["week_end", "project_key", "status"]).sum() == 0


def test_incremental_load_inserts_zero_on_rerun():
    wh = _loaded_wh()
    before = {t: len(df) for t, df in wh.tables.items() if t.startswith("fact_")}
    added = wh.build_facts()
    assert added == {}
    after = {t: len(df) for t, df in wh.tables.items() if t.startswith("fact_")}
    assert before == after


def test_watermarks_advance_to_latest_date():
    wh = _loaded_wh()
    assert wh.load_state["fact_ai_usage_daily"] == "2026-11-25"
    assert wh.load_state["fact_unit_economics_daily"] == "2026-11-25"


def test_lineage_lists_upstream_sources():
    wh = _loaded_wh()
    lineage = wh.lineage_for("fact_ai_usage_daily")
    assert "bronze_ai_usage" in lineage
    assert "source:ai_usage_events" in lineage
    assert "dim_tool" in lineage
    # a fact never feeds another fact
    assert "fact_cost_daily" not in lineage
    assert "fact_jira_weekly" not in lineage
