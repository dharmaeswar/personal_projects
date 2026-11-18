#!/usr/bin/env python3
"""Generate ``data/sample_surface.csv``.

The clean surface comes from a total-variance model

    w(k, T) = (0.04 + 0.02 * T) * (1 + 0.3 * k^2),   k = log(K / F)

which is non-decreasing in T for every strike (calendar-arbitrage free)
and produces smooth, convex call prices (butterfly-arbitrage free). The
generator first asserts the clean surface passes every check, then plants
three deliberate defects so the checker demonstrably flags them:

1. **Calendar violation** -- an extra lone quote at strike 100, T=0.75
   with implied vol 0.22: its total variance (0.0363) falls below the
   T=0.5 value (0.0500) at the same strike. It is planted as a single
   quote on its own expiry slice so it does not distort the price shape
   of any full expiry slice.
2. **Butterfly violation** -- strike 100, T=2.0: market price bumped by
   +1.20, breaking convexity of call prices in strike at that expiry.
3. **Stale quote** -- strike 120, T=2.0: timestamp left 10 days behind
   the rest of the file.
"""

from __future__ import annotations

import csv
import math
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vol_surface_checker.black_scholes import bs_price, implied_vol
from vol_surface_checker.checks import run_all_checks
from vol_surface_checker.surface import Quote, Surface

SPOT = 100.0
RATE = 0.03
EXPIRIES = (0.25, 0.5, 1.0, 2.0)
STRIKES = (80.0, 85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0)
FRESH_TS = datetime(2024, 2, 15, 9, 30, 0)
STALE_TS = datetime(2024, 2, 5, 9, 30, 0)


def model_vol(strike: float, expiry: float) -> float:
    forward = SPOT * math.exp(RATE * expiry)
    k = math.log(strike / forward)
    w = (0.04 + 0.02 * expiry) * (1.0 + 0.3 * k * k)
    return math.sqrt(w / expiry)


def build_quotes() -> list[Quote]:
    quotes = []
    for expiry in EXPIRIES:
        for strike in STRIKES:
            vol = model_vol(strike, expiry)
            quotes.append(
                Quote(
                    timestamp=FRESH_TS,
                    expiry=expiry,
                    strike=strike,
                    spot=SPOT,
                    rate=RATE,
                    option_type="call",
                    market_price=bs_price(SPOT, strike, expiry, RATE, vol),
                    implied_vol=vol,
                )
            )
    return quotes


def plant_violations(quotes: list[Quote]) -> list[Quote]:
    out = []
    # 1. Calendar violation: a lone T=0.75 quote at strike 100 whose total
    # variance (0.22^2 * 0.75 = 0.0363) is below the T=0.5 value (0.0500).
    bad_vol = 0.22
    out.append(
        Quote(
            timestamp=FRESH_TS,
            expiry=0.75,
            strike=100.0,
            spot=SPOT,
            rate=RATE,
            option_type="call",
            market_price=bs_price(SPOT, 100.0, 0.75, RATE, bad_vol),
            implied_vol=bad_vol,
        )
    )
    for q in quotes:
        if q.strike == 100.0 and q.expiry == 2.0:
            # 2. Butterfly violation: bump the price off the convex curve.
            bad_price = q.market_price + 1.20
            q = Quote(
                timestamp=q.timestamp,
                expiry=q.expiry,
                strike=q.strike,
                spot=q.spot,
                rate=q.rate,
                option_type=q.option_type,
                market_price=bad_price,
                implied_vol=implied_vol(bad_price, SPOT, q.strike, q.expiry, RATE),
            )
        elif q.strike == 120.0 and q.expiry == 2.0:
            # 3. Stale quote: timestamp 10 days behind the rest.
            q = Quote(
                timestamp=STALE_TS,
                expiry=q.expiry,
                strike=q.strike,
                spot=q.spot,
                rate=q.rate,
                option_type=q.option_type,
                market_price=q.market_price,
                implied_vol=q.implied_vol,
            )
        out.append(q)
    return out


def main() -> int:
    clean = build_quotes()
    report = run_all_checks(Surface(quotes=clean), max_age_hours=24.0)
    assert report.ok, f"clean surface should pass, got: {report.violations}"

    quotes = plant_violations(clean)
    planted = run_all_checks(Surface(quotes=quotes), max_age_hours=24.0)
    kinds = planted.counts_by_check()
    print("planted-violation check counts:", kinds)
    assert kinds.get("calendar_arbitrage") == 1, kinds
    assert kinds.get("butterfly_arbitrage") == 1, kinds
    assert kinds.get("stale_quote") == 1, kinds
    assert len(planted.violations) == 3, kinds
    quotes.sort(key=lambda q: (q.expiry, q.strike))

    out_path = Path(__file__).resolve().parent.parent / "data" / "sample_surface.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "timestamp",
                "expiry",
                "strike",
                "spot",
                "rate",
                "option_type",
                "market_price",
                "implied_vol",
            ]
        )
        for q in quotes:
            writer.writerow(
                [
                    q.timestamp.isoformat(),
                    f"{q.expiry:g}",
                    f"{q.strike:g}",
                    f"{q.spot:g}",
                    f"{q.rate:g}",
                    q.option_type,
                    f"{q.market_price:.6f}",
                    f"{q.implied_vol:.6f}",
                ]
            )
    print(f"wrote {len(quotes)} quotes to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
