"""Customer economics for a card-issuing portfolio.

Money is Decimal, rounded to cents. All figures are synthetic and seeded;
nothing here is real Marqeta data or a real customer.

Revenue per settled dollar of card volume (TPV):
  interchange revenue  = TPV * interchange_bps / 10_000
Costs per settled dollar:
  network fees         = TPV * network_bps / 10_000
  bank partner cost    = TPV * bank_bps / 10_000
  processing cost      = transactions * per_txn_fee
Gross profit = interchange revenue - network - bank - processing - fixed monthly cost.
"""
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PricingTerms:
    """Per-customer pricing terms, in basis points unless stated."""
    interchange_bps: Decimal   # revenue earned per $ of volume
    network_bps: Decimal       # card-network fees
    bank_bps: Decimal          # bank partner share
    per_txn_fee: Decimal       # processing cost per transaction, dollars
    fixed_monthly: Decimal     # fixed platform / support cost, dollars

    def __post_init__(self):
        for field in ("interchange_bps", "network_bps", "bank_bps"):
            if Decimal(str(getattr(self, field))) < 0:
                raise ValueError(f"{field} must not be negative")
        if self.per_txn_fee < 0 or self.fixed_monthly < 0:
            raise ValueError("fees and fixed cost must not be negative")


@dataclass(frozen=True)
class MonthActuals:
    """One customer's settled activity for one month."""
    customer: str
    month: str               # YYYY-MM
    tpv: Decimal             # total payment volume, dollars
    transactions: int

    def __post_init__(self):
        if self.tpv < 0:
            raise ValueError("tpv must not be negative")
        if self.transactions < 0:
            raise ValueError("transactions must not be negative")


@dataclass(frozen=True)
class MonthEconomics:
    customer: str
    month: str
    tpv: Decimal
    transactions: int
    interchange: Decimal
    network_fees: Decimal
    bank_cost: Decimal
    processing_cost: Decimal
    fixed_cost: Decimal
    gross_profit: Decimal
    gross_margin_pct: Decimal  # gross profit / interchange revenue * 100


def month_economics(actuals: MonthActuals, terms: PricingTerms) -> MonthEconomics:
    """Turn one month of settled activity into a gross-profit statement."""
    bps = Decimal("10000")
    interchange = money(actuals.tpv * terms.interchange_bps / bps)
    network = money(actuals.tpv * terms.network_bps / bps)
    bank = money(actuals.tpv * terms.bank_bps / bps)
    processing = money(Decimal(actuals.transactions) * terms.per_txn_fee)
    fixed = money(terms.fixed_monthly)
    profit = money(interchange - network - bank - processing - fixed)
    margin = (
        money(profit / interchange * 100) if interchange > 0 else Decimal("0.00")
    )
    return MonthEconomics(
        customer=actuals.customer,
        month=actuals.month,
        tpv=money(actuals.tpv),
        transactions=actuals.transactions,
        interchange=interchange,
        network_fees=network,
        bank_cost=bank,
        processing_cost=processing,
        fixed_cost=fixed,
        gross_profit=profit,
        gross_margin_pct=margin,
    )


def portfolio_totals(months: list) -> dict:
    """Sum a list of MonthEconomics into portfolio totals (Decimal, cents)."""
    total = {
        "tpv": Decimal("0.00"),
        "transactions": 0,
        "interchange": Decimal("0.00"),
        "network_fees": Decimal("0.00"),
        "bank_cost": Decimal("0.00"),
        "processing_cost": Decimal("0.00"),
        "fixed_cost": Decimal("0.00"),
        "gross_profit": Decimal("0.00"),
    }
    for m in months:
        total["tpv"] += m.tpv
        total["transactions"] += m.transactions
        total["interchange"] += m.interchange
        total["network_fees"] += m.network_fees
        total["bank_cost"] += m.bank_cost
        total["processing_cost"] += m.processing_cost
        total["fixed_cost"] += m.fixed_cost
        total["gross_profit"] += m.gross_profit
    total["gross_margin_pct"] = (
        money(total["gross_profit"] / total["interchange"] * 100)
        if total["interchange"] > 0
        else Decimal("0.00")
    )
    return total
