"""A free-float market-cap-weighted index universe.

An index level is total free-float market capitalisation divided by a
divisor. The divisor is set once (so the level starts at a chosen base,
here 1000) and only changes when a corporate action moves prices without
moving economic value, so the level is not distorted by the action.
"""

from dataclasses import dataclass


@dataclass
class Constituent:
    """One index constituent. Shares are in millions; market cap in $m."""

    ticker: str
    shares_outstanding: float  # millions of shares
    price: float  # per-share price in dollars
    free_float: float  # fraction of shares freely available, 0..1
    sector: str = ""

    @property
    def free_float_mcap(self) -> float:
        """Free-float market capitalisation, in $ millions."""
        return self.shares_outstanding * self.price * self.free_float


class IndexUniverse:
    """A set of constituents plus the divisor that defines the level."""

    def __init__(self, constituents, base_level=1000.0):
        self.constituents = {c.ticker: c for c in constituents}
        total = sum(c.free_float_mcap for c in constituents)
        if total <= 0:
            raise ValueError("total free-float market cap must be positive")
        self.divisor = total / base_level

    def total_mcap(self) -> float:
        """Total free-float market capitalisation, in $ millions."""
        return sum(c.free_float_mcap for c in self.constituents.values())

    def level(self) -> float:
        """Current index level: total free-float market cap / divisor."""
        return self.total_mcap() / self.divisor

    def weights(self) -> dict:
        """Constituent weights as fractions of total free-float market cap."""
        total = self.total_mcap()
        return {t: c.free_float_mcap / total for t, c in self.constituents.items()}

    def add(self, constituent: Constituent) -> None:
        self.constituents[constituent.ticker] = constituent

    def remove(self, ticker: str) -> None:
        del self.constituents[ticker]
