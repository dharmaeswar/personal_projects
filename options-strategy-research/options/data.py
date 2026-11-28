"""Synthetic market data for options research.

Generates a seeded geometric Brownian motion path for one underlying and
an option chain (strikes x expiries) priced off a volatility smile, then
stores both as CSV so the research pipeline reads from disk exactly like
it would read a real feed dump. Nothing here is real market data.
"""

import csv
import json
import math
import os
import random

from .pricing import call_price, put_price


def simulate_underlying(start=100.0, days=252, mu=0.05, sigma=0.25,
                        seed=42):
    """Daily underlying closes from a seeded GBM. Returns a list of floats."""
    rng = random.Random(seed)
    dt = 1.0 / 252.0
    prices = [start]
    for _ in range(days):
        shock = rng.gauss(0.0, 1.0)
        step = math.exp((mu - 0.5 * sigma * sigma) * dt
                        + sigma * math.sqrt(dt) * shock)
        prices.append(prices[-1] * step)
    return prices


def smile_vol(strike, spot, base_vol=0.25):
    """Simple smile: at-the-money vol is lowest, wings are higher."""
    moneyness = math.log(strike / spot)
    return base_vol + 0.10 * moneyness * moneyness


def build_chain(spot, expiries_days=(30, 60, 90), strikes=None, rate=0.05,
                base_vol=0.25, spread_bps=20):
    """Build an option chain as a list of quote dicts.

    Each quote carries spot, strike, expiry in days, kind, bid, ask, mid,
    and the vol the quote was generated from. Bid/ask straddle the
    Black-Scholes mid by half the spread.
    """
    if strikes is None:
        strikes = [round(spot * f, 2) for f in (0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15)]
    quotes = []
    for expiry_days in expiries_days:
        t = expiry_days / 365.0
        for strike in strikes:
            vol = smile_vol(strike, spot, base_vol)
            for kind in ("call", "put"):
                pricer = call_price if kind == "call" else put_price
                mid = pricer(spot, strike, t, rate, vol)
                half_spread = mid * spread_bps / 20000.0
                quotes.append({
                    "spot": spot, "strike": strike,
                    "expiry_days": expiry_days, "kind": kind,
                    "bid": round(mid - half_spread, 4),
                    "ask": round(mid + half_spread, 4),
                    "mid": round(mid, 4), "vol": round(vol, 4),
                })
    return quotes


def write_chain_csv(quotes, path):
    """Write quotes to CSV. Creates parent directories as needed."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fields = ["spot", "strike", "expiry_days", "kind", "bid", "ask", "mid", "vol"]
    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(quotes)
    return path


def read_chain_csv(path):
    """Read quotes back from CSV, restoring numeric types."""
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for key in ("spot", "strike", "bid", "ask", "mid", "vol"):
            row[key] = float(row[key])
        row["expiry_days"] = int(row["expiry_days"])
    return rows


def write_prices_json(prices, path):
    """Write the underlying price path to JSON."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump({"prices": prices}, fh)
    return path


def read_prices_json(path):
    """Read the underlying price path back from JSON."""
    with open(path) as fh:
        return json.load(fh)["prices"]
