"""AI spend management backend for the agent eval harness.

The spend-management side of an AI product: every agent/tool call costs
tokens and dollars, and a finance team needs to see who spent what, on
which model, against which budget — before the bill lands.

This module is the backend an "AI Spend Management" product would run on:
ingest spend events (token usage per agent run, per team, per model),
aggregate them, enforce budgets with warn/breach alerts, forecast
month-end spend, and flag daily spikes. All data is synthetic and local;
prices come from a fixed per-model table (harness constants, not real
vendor pricing), and nothing here talks to a real billing API.

Data models
------------
SpendRecord: one billed unit of AI usage — team, model, agent/tool,
prompt + completion tokens, cost in USD, and the day it happened.
Budget: a monthly USD cap for a team (optionally scoped to one model),
with warn and breach thresholds as fractions of the cap.

Public API (the shape an HTTP layer would wrap)
-----------------------------------------------
ingest_spend_event(payload) -> SpendRecord   (schema-validated, like tools.py)
SpendLedger.add(record) / ingest(payload)
ledger.summary(team=None, model=None) -> dict (totals, by team/model/day)
ledger.check_budgets() -> list[Alert]        (warn / breach / forecast)
ledger.daily_spike_alerts() -> list[Alert]
ledger.from_tracer(tracer, team, model)      (feed traced tool calls in)
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field

# Fixed per-model price table, USD per 1K tokens (prompt, completion).
# Made-up harness constants, not real vendor pricing.
MODEL_PRICES = {
    "gpt-4o": (0.0025, 0.010),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-sonnet": (0.003, 0.015),
    "claude-haiku": (0.00025, 0.00125),
    "llama-3-70b": (0.0004, 0.0004),
}

DEFAULT_MODEL = "gpt-4o-mini"
REQUIRED_EVENT_FIELDS = ("team", "model", "agent", "prompt_tokens",
                         "completion_tokens", "day")


class SpendError(ValueError):
    """Raised when a spend event or budget definition is invalid."""


@dataclass(frozen=True)
class SpendRecord:
    team: str
    model: str
    agent: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    day: str  # YYYY-MM-DD

    @property
    def total_tokens(self):
        return self.prompt_tokens + self.completion_tokens

    def to_dict(self):
        return {"team": self.team, "model": self.model, "agent": self.agent,
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "cost_usd": round(self.cost_usd, 6),
                "total_tokens": self.total_tokens, "day": self.day}


def price_tokens(model, prompt_tokens, completion_tokens):
    """Cost of a token split at the model's fixed per-1K-token prices."""
    if model not in MODEL_PRICES:
        raise SpendError(f"unknown model: {model}")
    prompt_price, completion_price = MODEL_PRICES[model]
    return (prompt_tokens / 1000.0 * prompt_price
            + completion_tokens / 1000.0 * completion_price)


def validate_spend_event(payload):
    """Validate a raw ingest payload; return a cleaned dict or raise."""
    if not isinstance(payload, dict):
        raise SpendError("spend event must be a JSON object")
    for key in REQUIRED_EVENT_FIELDS:
        if key not in payload:
            raise SpendError(f"spend event missing field: {key}")
    team, model, agent = (str(payload["team"]).strip(),
                          str(payload["model"]).strip(),
                          str(payload["agent"]).strip())
    if not team:
        raise SpendError("team must be a non-empty string")
    if not agent:
        raise SpendError("agent must be a non-empty string")
    if model not in MODEL_PRICES:
        raise SpendError(f"unknown model: {model}")
    for key in ("prompt_tokens", "completion_tokens"):
        value = payload[key]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SpendError(f"{key} must be a non-negative integer")
    day = str(payload["day"])
    parts = day.split("-")
    if len(parts) != 3 or len(parts[0]) != 4 or not all(p.isdigit() for p in parts):
        raise SpendError(f"day must be YYYY-MM-DD, got: {day}")
    year, month, day_num = (int(parts[0]), int(parts[1]), int(parts[2]))
    if not (1 <= month <= 12 and 1 <= day_num <= 31):
        raise SpendError(f"day must be a real calendar date, got: {day}")
    cost = payload.get("cost_usd")
    if cost is None:
        cost = price_tokens(model, payload["prompt_tokens"],
                            payload["completion_tokens"])
    else:
        if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
            raise SpendError("cost_usd must be a non-negative number")
    return {"team": team, "model": model, "agent": agent,
            "prompt_tokens": payload["prompt_tokens"],
            "completion_tokens": payload["completion_tokens"],
            "cost_usd": round(float(cost), 6), "day": day}


@dataclass
class Budget:
    team: str
    monthly_cap_usd: float
    model: str | None = None
    warn_frac: float = 0.8
    breach_frac: float = 1.0

    def __post_init__(self):
        if not self.team:
            raise SpendError("budget team must be a non-empty string")
        if self.monthly_cap_usd <= 0:
            raise SpendError("monthly cap must be positive")
        if self.model is not None and self.model not in MODEL_PRICES:
            raise SpendError(f"unknown model: {self.model}")
        if not (0 < self.warn_frac < self.breach_frac):
            raise SpendError("need 0 < warn_frac < breach_frac")


@dataclass
class Alert:
    level: str  # "warn", "breach", "forecast", "spike"
    team: str
    model: str | None
    message: str
    amount_usd: float

    def to_dict(self):
        return {"level": self.level, "team": self.team, "model": self.model,
                "message": self.message, "amount_usd": round(self.amount_usd, 6)}


class SpendLedger:
    """In-memory ledger: ingest events, aggregate, enforce budgets."""

    def __init__(self):
        self.records: list[SpendRecord] = []
        self.budgets: list[Budget] = []

    def ingest(self, payload):
        """Validate one event dict and append it; return the record."""
        record = SpendRecord(**validate_spend_event(payload))
        self.records.append(record)
        return record

    def add(self, record):
        if not isinstance(record, SpendRecord):
            raise SpendError("add() needs a SpendRecord; use ingest() for dicts")
        self.records.append(record)
        return record

    def set_budget(self, budget):
        if not isinstance(budget, Budget):
            raise SpendError("set_budget() needs a Budget")
        self.budgets = [b for b in self.budgets
                        if not (b.team == budget.team and b.model == budget.model)]
        self.budgets.append(budget)
        return budget

    def _scope(self, team=None, model=None):
        return [r for r in self.records
                if (team is None or r.team == team)
                and (model is None or r.model == model)]

    def summary(self, team=None, model=None):
        """Totals plus per-team, per-model and per-day breakdowns."""
        rows = self._scope(team, model)
        by_team, by_model, by_day = {}, {}, {}
        for r in rows:
            by_team[r.team] = by_team.get(r.team, 0.0) + r.cost_usd
            by_model[r.model] = by_model.get(r.model, 0.0) + r.cost_usd
            by_day[r.day] = by_day.get(r.day, 0.0) + r.cost_usd
        return {
            "event_count": len(rows),
            "total_tokens": sum(r.total_tokens for r in rows),
            "total_cost_usd": round(sum(r.cost_usd for r in rows), 6),
            "by_team": {k: round(v, 6) for k, v in sorted(by_team.items())},
            "by_model": {k: round(v, 6) for k, v in sorted(by_model.items())},
            "by_day": {k: round(v, 6) for k, v in sorted(by_day.items())},
        }

    def month_spend(self, team, model=None, year_month=None):
        """Spend for one team (optionally one model) in a YYYY-MM month."""
        rows = self._scope(team, model)
        if year_month is None and rows:
            year_month = sorted({r.day[:7] for r in rows})[-1]
        rows = [r for r in rows if r.day.startswith(year_month or "")]
        return round(sum(r.cost_usd for r in rows), 6), sorted({r.day for r in rows})

    def check_budgets(self, year_month=None):
        """Warn/breach alerts plus a forecast alert when the run rate
        projects past the cap by month end."""
        alerts = []
        for budget in self.budgets:
            spent, days = self.month_spend(budget.team, budget.model, year_month)
            if spent >= budget.monthly_cap_usd * budget.breach_frac:
                alerts.append(Alert(
                    "breach", budget.team, budget.model,
                    f"{budget.team} spent ${spent:.2f} of "
                    f"${budget.monthly_cap_usd:.2f} budget",
                    spent))
            elif spent >= budget.monthly_cap_usd * budget.warn_frac:
                alerts.append(Alert(
                    "warn", budget.team, budget.model,
                    f"{budget.team} spent ${spent:.2f} of "
                    f"${budget.monthly_cap_usd:.2f} budget "
                    f"({spent / budget.monthly_cap_usd:.0%} used)",
                    spent))
            if len(days) >= 3 and year_month is None:
                year, month = int(days[0][:4]), int(days[0][5:7])
            elif year_month:
                year, month = int(year_month[:4]), int(year_month[5:7])
            else:
                continue
            days_in_month = calendar.monthrange(year, month)[1]
            elapsed = max(len(days), 1)
            projected = spent / elapsed * days_in_month
            if projected > budget.monthly_cap_usd and spent < budget.monthly_cap_usd:
                alerts.append(Alert(
                    "forecast", budget.team, budget.model,
                    f"{budget.team} on pace for ${projected:.2f} this month "
                    f"vs ${budget.monthly_cap_usd:.2f} budget",
                    round(projected, 6)))
        return alerts

    def daily_spike_alerts(self, team=None, factor=2.0):
        """Flag any day whose spend is over `factor` x the mean of the
        other days for the same team (needs at least 3 days of data)."""
        alerts = []
        teams = sorted({r.team for r in self.records
                        if team is None or r.team == team})
        for t in teams:
            by_day = {}
            for r in self.records:
                if r.team == t:
                    by_day[r.day] = by_day.get(r.day, 0.0) + r.cost_usd
            if len(by_day) < 3:
                continue
            for day, amount in sorted(by_day.items()):
                others = [v for d, v in by_day.items() if d != day]
                mean = sum(others) / len(others)
                if mean > 0 and amount > factor * mean:
                    alerts.append(Alert(
                        "spike", t, None,
                        f"{t} spent ${amount:.2f} on {day}, "
                        f"{amount / mean:.1f}x the daily mean ${mean:.2f}",
                        round(amount, 6)))
        return alerts

    def from_tracer(self, tracer, team, model=DEFAULT_MODEL, day="2026-11-25",
                    agent="eval-agent"):
        """Feed a finished Tracer into the ledger: each traced tool call
        becomes one spend event, priced at the model's per-token rates.
        The tracer's fixed per-tool token model supplies the token split
        (80% prompt / 20% completion); cost is recomputed from tokens."""
        from .tracer import TOOL_COST_MODEL
        ingested = []
        for call in tracer.calls:
            tokens = TOOL_COST_MODEL.get(call.tool, {"tokens": 100})["tokens"]
            prompt = int(tokens * 0.8)
            completion = tokens - prompt
            ingested.append(self.ingest({
                "team": team, "model": model, "agent": agent,
                "prompt_tokens": prompt, "completion_tokens": completion,
                "day": day}))
        return ingested
