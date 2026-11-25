"""Leverage and funding risk for municipal portfolios: tender option bonds (TOBs) and variable-rate municipal term preferred (VMTP).

A leveraged municipal strategy holds long-term tax-exempt bonds inside a
trust and funds part of the purchase by selling short-term floating-rate
notes (the "floaters") to money-market buyers; the residual (inverse
floater) keeps the remaining economics. Leverage magnifies the yield of the
underlying bonds, but the funding leg resets at short-term rates, so a
rise in remarketing rates eats the distribution and can force a sale of
the underlying bonds. VMTP is the other common funding leg: preferred
shares whose dividend resets periodically and which carry a remarketing
spread on top of the base rate.

All figures here are synthetic and seeded in the demo. No real issuer,
CUSIP, or market data appears anywhere in this project.
"""

from dataclasses import dataclass


@dataclass
class TobStructure:
    """A tender option bond trust. All amounts are par values; all rates
    are annual decimals (0.045 = 4.5%)."""

    underlying_par: float       # par of the long-term muni bonds in the trust
    floater_par: float          # par of short-term floaters sold to fund them
    underlying_yield: float     # annual yield earned on the underlying bonds
    floater_rate: float         # current annual remarketing rate on the floaters
    liquidity_fee_bps: float = 0.0    # annual liquidity-facility fee, bp of floater par
    remarketing_fee_bps: float = 0.0  # annual remarketing fee, bp of floater par

    def __post_init__(self):
        if self.underlying_par <= 0 or self.floater_par <= 0:
            raise ValueError("par values must be positive")
        if self.floater_par >= self.underlying_par:
            raise ValueError("floater par must be below underlying par")
        if self.underlying_yield < 0 or self.floater_rate < 0:
            raise ValueError("rates must be >= 0")

    @property
    def residual_par(self):
        """Equity in the trust: the inverse floater's par."""
        return self.underlying_par - self.floater_par

    @property
    def leverage_ratio(self):
        """Assets per unit of residual equity (4.0 = 75% funded by floaters)."""
        return self.underlying_par / self.residual_par

    def funding_cost_annual(self):
        """Annual cost of the floater leg: remarketing rate plus fees."""
        fee_rate = (self.liquidity_fee_bps + self.remarketing_fee_bps) / 10000.0
        return self.floater_par * (self.floater_rate + fee_rate)

    def residual_income_annual(self):
        """Annual income left for the residual holder after funding costs."""
        return self.underlying_par * self.underlying_yield - self.funding_cost_annual()

    def residual_yield(self):
        """Annualised yield on the residual (inverse floater) par."""
        return self.residual_income_annual() / self.residual_par

    def distribution_coverage(self, target_distribution_annual):
        """Residual income divided by the target annual distribution.

        Above 1.0 the distribution is covered; below 1.0 the trust pays
        out more than it earns and the shortfall comes out of principal.
        """
        if target_distribution_annual <= 0:
            raise ValueError("target distribution must be positive")
        return self.residual_income_annual() / target_distribution_annual


def funding_shock_scenarios(tob, target_distribution_annual,
                            rate_shocks_bp=(-50, 0, 50, 100, 200)):
    """Residual economics if the floater remarketing rate moves.

    Returns ``{shock_bp: {floater_rate, funding_cost, residual_yield,
    distribution_coverage}}``. The +100bp and +200bp rows are the funding
    stress test: a leveraged muni trust fails first through its funding
    leg, not through its bonds.
    """
    out = {}
    for shock in rate_shocks_bp:
        stressed = TobStructure(
            underlying_par=tob.underlying_par,
            floater_par=tob.floater_par,
            underlying_yield=tob.underlying_yield,
            floater_rate=tob.floater_rate + shock / 10000.0,
            liquidity_fee_bps=tob.liquidity_fee_bps,
            remarketing_fee_bps=tob.remarketing_fee_bps,
        )
        out[shock] = {
            "floater_rate_pct": round(stressed.floater_rate * 100, 3),
            "funding_cost": round(stressed.funding_cost_annual(), 4),
            "residual_yield_pct": round(stressed.residual_yield() * 100, 3),
            "distribution_coverage": round(
                stressed.distribution_coverage(target_distribution_annual), 3),
        }
    return out


def vmtp_cost(preferred_par, dividend_rate, remarketing_spread_bps=0.0):
    """Annual cost of a VMTP funding leg.

    Returns ``{"annual_cost": ..., "cost_per_100_par": ...}`` — the
    dividend on the preferred shares plus the remarketing spread, both
    annualised. VMTP has no liquidity-facility fee in this model; the
    spread is the market's price for remarketing risk.
    """
    if preferred_par <= 0 or dividend_rate < 0:
        raise ValueError("preferred par must be positive and rate >= 0")
    annual_cost = preferred_par * (dividend_rate + remarketing_spread_bps / 10000.0)
    return {
        "annual_cost": round(annual_cost, 4),
        "cost_per_100_par": round(annual_cost / preferred_par * 100, 4),
    }


def leverage_risk_summary(tob, target_distribution_annual):
    """One-line risk verdict for a TOB trust.

    Flags FUNDING STRESS when a +100bp rise in the floater rate would
    leave the target distribution uncovered — the point at which leverage
    stops adding return and starts consuming principal.
    """
    scenarios = funding_shock_scenarios(tob, target_distribution_annual)
    coverage_100 = scenarios[100]["distribution_coverage"]
    return {
        "leverage_ratio": round(tob.leverage_ratio, 2),
        "residual_yield_pct": round(tob.residual_yield() * 100, 3),
        "distribution_coverage": round(
            tob.distribution_coverage(target_distribution_annual), 3),
        "coverage_at_plus_100bp": coverage_100,
        "verdict": ("FUNDING STRESS" if coverage_100 < 1.0
                    else "COVERED AT +100BP"),
    }
