"""Tests for the AI spend-management backend (agent_eval/spend.py)."""

import pytest

from agent_eval.spend import (Alert, Budget, SpendError, SpendLedger,
                              SpendRecord, price_tokens, validate_spend_event)
from agent_eval.tracer import Tracer


def _event(team="finance", model="gpt-4o-mini", day="2026-11-03",
           prompt=1000, completion=500, agent="invoice-agent"):
    return {"team": team, "model": model, "agent": agent,
            "prompt_tokens": prompt, "completion_tokens": completion,
            "day": day}


def test_price_tokens_uses_model_table():
    # gpt-4o-mini: 1000 prompt @ 0.00015 + 500 completion @ 0.0006
    assert price_tokens("gpt-4o-mini", 1000, 500) == pytest.approx(0.00045)
    with pytest.raises(SpendError):
        price_tokens("no-such-model", 10, 10)


def test_ingest_prices_from_tokens_when_cost_missing():
    ledger = SpendLedger()
    record = ledger.ingest(_event())
    assert record.cost_usd == pytest.approx(0.00045)
    assert record.total_tokens == 1500
    assert record.to_dict()["team"] == "finance"


def test_ingest_rejects_bad_events():
    ledger = SpendLedger()
    bad = _event()
    del bad["team"]
    with pytest.raises(SpendError):
        ledger.ingest(bad)
    with pytest.raises(SpendError):
        ledger.ingest(_event(model="unknown-model"))
    with pytest.raises(SpendError):
        ledger.ingest(_event(prompt=-5))
    with pytest.raises(SpendError):
        ledger.ingest(_event(prompt=10.5))
    with pytest.raises(SpendError):
        ledger.ingest(_event(day="Nov 3"))
    with pytest.raises(SpendError):
        ledger.ingest("not a dict")
    with pytest.raises(SpendError):
        ledger.ingest({**_event(), "cost_usd": -1})


def test_explicit_cost_is_kept():
    ledger = SpendLedger()
    record = ledger.ingest({**_event(), "cost_usd": 0.02})
    assert record.cost_usd == pytest.approx(0.02)


def test_summary_aggregates_by_team_model_day():
    ledger = SpendLedger()
    ledger.ingest(_event(team="finance", model="gpt-4o-mini"))
    ledger.ingest(_event(team="finance", model="claude-sonnet", day="2026-11-04"))
    ledger.ingest(_event(team="support", model="gpt-4o-mini", day="2026-11-03"))
    summary = ledger.summary()
    assert summary["event_count"] == 3
    assert summary["total_tokens"] == 4500
    assert summary["by_team"]["finance"] == pytest.approx(0.00045 + 0.0105)
    assert summary["by_team"]["support"] == pytest.approx(0.00045)
    assert summary["by_day"]["2026-11-03"] == pytest.approx(0.0009)
    assert ledger.summary(team="support")["event_count"] == 1
    assert ledger.summary(model="claude-sonnet")["event_count"] == 1


def test_budget_warn_and_breach():
    ledger = SpendLedger()
    ledger.set_budget(Budget(team="finance", monthly_cap_usd=0.01))
    ledger.ingest(_event(prompt=1000, completion=500))  # $0.00045, under warn
    assert ledger.check_budgets() == []
    ledger.ingest(_event(prompt=10000, completion=10000, day="2026-11-04"))
    # spend now $0.00045 + $0.0075 = $0.00795 -> under 80% warn? 0.00795 < 0.008
    assert ledger.check_budgets() == []
    ledger.ingest(_event(prompt=10000, completion=10000, day="2026-11-05"))
    alerts = ledger.check_budgets()
    assert any(a.level == "breach" for a in alerts)
    assert all(isinstance(a, Alert) for a in alerts)


def test_budget_warn_level():
    ledger = SpendLedger()
    ledger.set_budget(Budget(team="finance", monthly_cap_usd=0.001))
    ledger.ingest(_event(prompt=1000, completion=500))  # $0.00045 = 45% of cap
    assert ledger.check_budgets() == []
    ledger.ingest(_event(prompt=1000, completion=500, day="2026-11-04"))
    # $0.0009 = 90% of cap -> warn, and forecast may also fire
    levels = [a.level for a in ledger.check_budgets()]
    assert "warn" in levels
    assert "breach" not in levels


def test_budget_validation():
    with pytest.raises(SpendError):
        Budget(team="finance", monthly_cap_usd=0)
    with pytest.raises(SpendError):
        Budget(team="finance", monthly_cap_usd=10, model="nope")
    with pytest.raises(SpendError):
        Budget(team="finance", monthly_cap_usd=10, warn_frac=0.9, breach_frac=0.8)
    ledger = SpendLedger()
    with pytest.raises(SpendError):
        ledger.set_budget("not a budget")


def test_budget_replace_same_scope():
    ledger = SpendLedger()
    ledger.set_budget(Budget(team="finance", monthly_cap_usd=10))
    ledger.set_budget(Budget(team="finance", monthly_cap_usd=20))
    assert len(ledger.budgets) == 1
    assert ledger.budgets[0].monthly_cap_usd == 20


def test_forecast_alert_when_run_rate_exceeds_cap():
    ledger = SpendLedger()
    # 3 days at $0.006/day projects to $0.18 in a 30-day month > $0.10 cap.
    ledger.set_budget(Budget(team="finance", monthly_cap_usd=0.10))
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        ledger.ingest(_event(day=day, prompt=20000, completion=5000))
    levels = [a.level for a in ledger.check_budgets(year_month="2026-11")]
    assert "forecast" in levels
    assert "breach" not in levels
    assert "warn" not in levels


def test_daily_spike_alert():
    ledger = SpendLedger()
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        ledger.ingest(_event(day=day, prompt=1000, completion=500))
    ledger.ingest(_event(day="2026-11-04", prompt=100000, completion=50000))
    alerts = ledger.daily_spike_alerts()
    assert len(alerts) == 1
    assert alerts[0].level == "spike"
    assert alerts[0].team == "finance"
    assert "2026-11-04" in alerts[0].message


def test_no_spike_with_fewer_than_three_days():
    ledger = SpendLedger()
    ledger.ingest(_event(day="2026-11-01", prompt=1000, completion=500))
    ledger.ingest(_event(day="2026-11-02", prompt=100000, completion=50000))
    assert ledger.daily_spike_alerts() == []


def test_from_tracer_ingests_tool_calls():
    tracer = Tracer()
    tracer.record("lookup_invoice", {"id": "INV-1"}, "ok")
    tracer.record("search_kb", {"q": "refund"}, "ok")
    ledger = SpendLedger()
    records = ledger.from_tracer(tracer, team="finance")
    assert len(records) == 2
    assert ledger.summary()["event_count"] == 2
    assert all(r.team == "finance" for r in records)
    assert all(r.cost_usd > 0 for r in records)


def test_add_requires_record():
    ledger = SpendLedger()
    with pytest.raises(SpendError):
        ledger.add({"team": "finance"})
    record = SpendRecord(team="finance", model="gpt-4o-mini", agent="a",
                         prompt_tokens=10, completion_tokens=10,
                         cost_usd=0.001, day="2026-11-03")
    assert ledger.add(record) is record


def test_validate_event_rejects_bad_date_values():
    with pytest.raises(SpendError):
        validate_spend_event(_event(day="2026-13-01"))
    with pytest.raises(SpendError):
        validate_spend_event(_event(day="2026-11-32"))
