"""Data model for the post-trade reconciliation service.

All records are plain dataclasses. Nothing here claims a live trading
connection: executions and clearing records are inputs the service
ingests, enriches, reconciles and stores.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Execution:
    """One executed trade as reported by the trading desk / venue."""

    exec_id: str
    symbol: str  # OCC-style option symbol, e.g. AAPL 260117C00250000
    side: str  # BUY or SELL
    quantity: int
    price: float
    trade_date: str  # YYYY-MM-DD
    venue: str
    account: str


@dataclass(frozen=True)
class ClearingRecord:
    """One cleared trade as reported by the clearing house."""

    clearing_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    trade_date: str
    account: str
    fees: float = 0.0


@dataclass(frozen=True)
class Instrument:
    """Reference data for one tradable instrument."""

    symbol: str
    underlying: str
    option_type: str  # CALL, PUT or EQUITY
    expiry: str  # YYYY-MM-DD, empty for equities
    strike: float
    multiplier: int
    currency: str
    exchange: str
    tick_size: float


@dataclass
class EnrichedTrade:
    """An execution joined to its instrument reference data."""

    execution: Execution
    instrument: Instrument | None
    notional: float
    enriched: bool
    enrichment_notes: list = field(default_factory=list)


@dataclass(frozen=True)
class Match:
    """A reconciled execution / clearing pair."""

    execution: Execution
    clearing: ClearingRecord
    status: str  # MATCHED or MATCHED_WITH_PRICE_VARIANCE
    price_difference: float = 0.0


@dataclass(frozen=True)
class Break:
    """A reconciliation break that needs middle-office review."""

    break_type: str  # MISSING_CLEARING, MISSING_EXECUTION, QTY_MISMATCH, PRICE_BREAK
    execution: Execution | None
    clearing: ClearingRecord | None
    detail: str


@dataclass(frozen=True)
class Position:
    """Net position in one instrument for one account."""

    account: str
    symbol: str
    net_quantity: int
    average_cost: float
    multiplier: int


@dataclass(frozen=True)
class SymbolPnl:
    """Realised and unrealised P&L for one account / symbol."""

    account: str
    symbol: str
    realised: float
    unrealised: float
    net_quantity: int
