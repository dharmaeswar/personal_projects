"""Option strategy payoffs at expiry.

Each strategy is a list of legs: (kind, strike, quantity, premium).
Quantity is +1 for a long leg and -1 for a short leg; premium is the
price paid (positive) or received (negative) per leg at trade time.
``payoff`` returns the strategy P&L at expiry for a given underlying
price, net of premiums.
"""

from .pricing import call_price, put_price


def leg_payoff(kind, strike, spot_at_expiry):
    """Intrinsic value of one option leg at expiry."""
    if kind == "call":
        return max(spot_at_expiry - strike, 0.0)
    if kind == "put":
        return max(strike - spot_at_expiry, 0.0)
    raise ValueError("kind must be 'call' or 'put'")


def strategy_payoff(legs, spot_at_expiry):
    """Net P&L of a strategy at expiry: intrinsic minus premiums paid."""
    total = 0.0
    for leg in legs:
        if leg["kind"] == "underlying":
            intrinsic = spot_at_expiry
        else:
            intrinsic = leg_payoff(leg["kind"], leg["strike"], spot_at_expiry)
        total += leg["quantity"] * (intrinsic - leg["premium"])
    return total


def build_straddle(spot, expiry_days, rate, vol, quantity=1):
    """Long at-the-money straddle: buy the ATM call and the ATM put."""
    t = expiry_days / 365.0
    strike = round(spot)
    legs = [
        {"kind": "call", "strike": strike, "quantity": quantity,
         "premium": call_price(spot, strike, t, rate, vol)},
        {"kind": "put", "strike": strike, "quantity": quantity,
         "premium": put_price(spot, strike, t, rate, vol)},
    ]
    return legs


def build_covered_call(spot, strike, rate, vol, expiry_days, quantity=1):
    """Covered call: long the underlying, short an out-of-the-money call.

    The underlying leg is modelled as a leg with zero strike premium
    equal to the spot; its expiry payoff is the spot itself.
    """
    t = expiry_days / 365.0
    premium = call_price(spot, strike, t, rate, vol)
    return [
        {"kind": "underlying", "strike": 0.0, "quantity": quantity,
         "premium": spot},
        {"kind": "call", "strike": strike, "quantity": -quantity,
         "premium": premium},
    ]


def build_iron_condor(spot, lower_put, upper_put, lower_call, upper_call,
                      expiry_days, rate, vol):
    """Iron condor: short an inner put spread and an inner call spread."""
    t = expiry_days / 365.0

    def price(kind, strike):
        pricer = call_price if kind == "call" else put_price
        return pricer(spot, strike, t, rate, vol)

    return [
        {"kind": "put", "strike": lower_put, "quantity": 1,
         "premium": price("put", lower_put)},
        {"kind": "put", "strike": upper_put, "quantity": -1,
         "premium": price("put", upper_put)},
        {"kind": "call", "strike": lower_call, "quantity": -1,
         "premium": price("call", lower_call)},
        {"kind": "call", "strike": upper_call, "quantity": 1,
         "premium": price("call", upper_call)},
    ]


def payoff_curve(legs, spots):
    """P&L of a strategy across a list of expiry underlying prices."""
    return [(spot, strategy_payoff(legs, spot)) for spot in spots]


def max_loss(legs, spots):
    """Worst P&L across the sampled expiry prices (a loss is negative)."""
    return min(pnl for _, pnl in payoff_curve(legs, spots))


def max_gain(legs, spots):
    """Best P&L across the sampled expiry prices."""
    return max(pnl for _, pnl in payoff_curve(legs, spots))
