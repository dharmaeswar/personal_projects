"""Trade enrichment: join executions to instrument reference data.

Enrichment adds the fields the middle office needs before a trade can
be reconciled, booked and risk-checked: underlying, option type, expiry,
strike, contract multiplier, currency, exchange and tick size. A trade
whose symbol is missing from reference data is kept in the flow and
flagged, never dropped silently.
"""

from .models import EnrichedTrade, Execution, Instrument

# Seeded reference data (synthetic, for the demo and tests). A real
# deployment loads this from the firm's security master.
REFERENCE_DATA = {
    "AAPL 260117C00250000": Instrument(
        symbol="AAPL 260117C00250000",
        underlying="AAPL",
        option_type="CALL",
        expiry="2026-01-17",
        strike=250.00,
        multiplier=100,
        currency="USD",
        exchange="CBOE",
        tick_size=0.01,
    ),
    "SPX 260117P00590000": Instrument(
        symbol="SPX 260117P00590000",
        underlying="SPX",
        option_type="PUT",
        expiry="2026-01-17",
        strike=5900.00,
        multiplier=100,
        currency="USD",
        exchange="CBOE",
        tick_size=0.05,
    ),
    "MSFT 260117C00420000": Instrument(
        symbol="MSFT 260117C00420000",
        underlying="MSFT",
        option_type="CALL",
        expiry="2026-01-17",
        strike=420.00,
        multiplier=100,
        currency="USD",
        exchange="NYSE ARCA",
        tick_size=0.01,
    ),
    "AAPL": Instrument(
        symbol="AAPL",
        underlying="AAPL",
        option_type="EQUITY",
        expiry="",
        strike=0.0,
        multiplier=1,
        currency="USD",
        exchange="NASDAQ",
        tick_size=0.01,
    ),
    "MSFT": Instrument(
        symbol="MSFT",
        underlying="MSFT",
        option_type="EQUITY",
        expiry="",
        strike=0.0,
        multiplier=1,
        currency="USD",
        exchange="NASDAQ",
        tick_size=0.01,
    ),
}


def enrich(execution: Execution, reference: dict | None = None) -> EnrichedTrade:
    """Enrich one execution; unknown symbols are flagged, not dropped."""
    ref = reference if reference is not None else REFERENCE_DATA
    instrument = ref.get(execution.symbol)
    if instrument is None:
        return EnrichedTrade(
            execution=execution,
            instrument=None,
            notional=execution.quantity * execution.price,
            enriched=False,
            enrichment_notes=[f"unknown instrument: {execution.symbol}"],
        )
    notes = []
    if instrument.exchange != execution.venue:
        notes.append(
            f"venue {execution.venue} differs from listing exchange "
            f"{instrument.exchange}"
        )
    return EnrichedTrade(
        execution=execution,
        instrument=instrument,
        notional=execution.quantity * execution.price * instrument.multiplier,
        enriched=True,
        enrichment_notes=notes,
    )


def enrich_all(executions, reference: dict | None = None) -> list[EnrichedTrade]:
    """Enrich a batch of executions in input order."""
    return [enrich(exc, reference) for exc in executions]
