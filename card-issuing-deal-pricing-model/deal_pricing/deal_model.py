"""Deal modeling: price a proposed deal against current terms.

A deal changes pricing terms (interchange share, network/bank bps, per-txn
fee, fixed cost) and/or commits volume. The model answers the questions a
sales negotiation needs:
  - incremental gross profit per month vs current terms, at the same volume;
  - break-even volume: the TPV at which the deal earns what current terms
    earn at the committed volume;
  - sensitivity: incremental profit at +/-10% and +/-20% volume.
All money is Decimal, rounded to cents. No deal is ever "approved" here;
the model only prices it.
"""
from dataclasses import dataclass
from decimal import Decimal

from .economics import MonthActuals, PricingTerms, month_economics, money


@dataclass(frozen=True)
class DealResult:
    customer: str
    month: str
    current_gross_profit: Decimal
    deal_gross_profit: Decimal
    incremental_gross_profit: Decimal
    incremental_margin_bps: Decimal  # incremental profit / TPV * 10_000
    break_even_tpv: Decimal | None   # None when the deal can never break even
    sensitivity: dict                # volume change pct -> incremental profit


def _profit_at_tpv(tpv: Decimal, transactions: int, terms: PricingTerms) -> Decimal:
    econ = month_economics(
        MonthActuals(customer="x", month="0000-00", tpv=tpv,
                     transactions=transactions),
        terms,
    )
    return econ.gross_profit


def model_deal(customer: str, month: str, tpv: Decimal, transactions: int,
               current_terms: PricingTerms, deal_terms: PricingTerms) -> DealResult:
    """Price a deal at the stated volume and find its break-even TPV."""
    if tpv <= 0:
        raise ValueError("tpv must be positive")
    if transactions < 0:
        raise ValueError("transactions must not be negative")
    current = _profit_at_tpv(tpv, transactions, current_terms)
    deal = _profit_at_tpv(tpv, transactions, deal_terms)
    incremental = money(deal - current)
    margin_bps = (
        money(incremental / tpv * Decimal("10000")) if tpv > 0 else Decimal("0.00")
    )

    # Break-even: smallest TPV where deal profit >= current profit at the
    # committed volume. Deal profit is linear in TPV at fixed txn/T PV ratio,
    # so solve by bisection on [0, 10x committed TPV].
    break_even = None
    txn_ratio = Decimal(transactions) / tpv  # txns per $ of volume, held fixed
    lo, hi = Decimal("0"), tpv * Decimal("10")
    if _profit_at_tpv(hi, int(hi * txn_ratio), deal_terms) >= current:
        for _ in range(60):
            mid = (lo + hi) / 2
            if _profit_at_tpv(mid, int(mid * txn_ratio), deal_terms) >= current:
                hi = mid
            else:
                lo = mid
        break_even = money(hi)

    sensitivity = {}
    for pct in (-20, -10, 10, 20):
        scaled_tpv = money(tpv * (Decimal("100") + Decimal(pct)) / Decimal("100"))
        scaled_txns = int(Decimal(transactions)
                          * (Decimal("100") + Decimal(pct)) / Decimal("100"))
        sensitivity[pct] = money(
            _profit_at_tpv(scaled_tpv, scaled_txns, deal_terms)
            - _profit_at_tpv(scaled_tpv, scaled_txns, current_terms)
        )
    return DealResult(
        customer=customer, month=month,
        current_gross_profit=current, deal_gross_profit=deal,
        incremental_gross_profit=incremental,
        incremental_margin_bps=margin_bps,
        break_even_tpv=break_even, sensitivity=sensitivity,
    )
