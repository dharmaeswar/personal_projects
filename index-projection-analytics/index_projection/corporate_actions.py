"""Corporate-action adjustments that keep the index level continuous.

A split changes shares and price in opposite directions, so market cap
(and therefore the level) is unchanged and the divisor stays put. A cash
dividend or a spin-off lowers the price without lowering economic value
held, so the divisor is scaled by the same ratio as total market cap to
hold the level constant.
"""

from .universe import Constituent, IndexUniverse


def apply_split(universe: IndexUniverse, ticker: str, factor: float) -> float:
    """Apply a stock split (factor 2 = 2-for-1). Returns the index level."""
    c = universe.constituents[ticker]
    c.shares_outstanding *= factor
    c.price /= factor
    return universe.level()


def apply_cash_dividend(universe: IndexUniverse, ticker: str, dividend: float) -> float:
    """Apply a cash dividend of `dividend` dollars per share.

    The price drops by the dividend and the divisor is rescaled so the
    index level is unchanged. Returns the index level.
    """
    before = universe.total_mcap()
    c = universe.constituents[ticker]
    if dividend >= c.price:
        raise ValueError("dividend must be smaller than the share price")
    c.price -= dividend
    after = universe.total_mcap()
    universe.divisor *= after / before
    return universe.level()


def apply_spinoff(
    universe: IndexUniverse,
    ticker: str,
    value_per_share: float,
    child_ticker: str,
    child_sector: str = "",
) -> float:
    """Apply a spin-off worth `value_per_share` per parent share.

    The parent price drops by the spun-off value and the spun-off company
    joins the index as a new constituent with the same share count and
    free float as the parent. The divisor is rescaled so the index level
    is unchanged. Returns the index level.
    """
    before = universe.total_mcap()
    parent = universe.constituents[ticker]
    if value_per_share >= parent.price:
        raise ValueError("spin-off value must be smaller than the share price")
    parent.price -= value_per_share
    universe.add(
        Constituent(
            ticker=child_ticker,
            shares_outstanding=parent.shares_outstanding,
            price=value_per_share,
            free_float=parent.free_float,
            sector=child_sector or parent.sector,
        )
    )
    after = universe.total_mcap()
    universe.divisor *= after / before
    return universe.level()
