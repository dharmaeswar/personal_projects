"""Demo: validate a seeded synthetic option book against Black-Scholes prices.

Builds 18 European option contracts (calls and puts, strikes 90/100/110,
expiries 0.25/0.5/1.0 years), marks them at model prices with small seeded
noise, and deliberately misprices one contract. Prints a validation summary
and writes options_validation_report.json.
"""
import json
import random

from model_validation_toolkit.options import validate_option_book

random.seed(42)

CONTRACTS = []
for expiry in (0.25, 0.5, 1.0):
    for strike in (90.0, 100.0, 110.0):
        for option_type in ("call", "put"):
            CONTRACTS.append({
                "spot": 100.0,
                "strike": strike,
                "rate": 0.05,
                "time_to_expiry": expiry,
                "vol": 0.20,
                "option_type": option_type,
                "market_price": None,  # filled below from the model price
            })

# Price each contract with the model, add up to 1% seeded noise to the mark,
# then deliberately misprice the 110-strike 1-year call by +25%.
from model_validation_toolkit.options import black_scholes_price

for c in CONTRACTS:
    model = black_scholes_price(c["spot"], c["strike"], c["rate"],
                                c["time_to_expiry"], c["vol"], c["option_type"])
    c["market_price"] = round(model * (1.0 + random.uniform(-0.005, 0.005)), 4)

mispriced = [c for c in CONTRACTS
             if c["strike"] == 110.0 and c["time_to_expiry"] == 1.0
             and c["option_type"] == "call"][0]
mispriced["market_price"] = round(mispriced["market_price"] * 1.25, 4)

report = validate_option_book(CONTRACTS, tolerance=0.05, parity_tolerance=0.10)

print(f"Contracts validated: {report['contracts']}")
print(f"Price breaches (>5% from model): {report['breaches']}")
print(f"Put-call parity breaches: {report['parity_breaches']}")
print(f"Worst relative error: {report['worst_relative_error']:.1%} "
      f"(contract {report['worst_index']})")
for r in report["results"]:
    flag = "BREACH" if r["breach"] else "pass"
    print(f"  [{r['index']:>2}] {r['option_type']:>4} K={r['strike']:.0f} "
          f"T={r['time_to_expiry']:.2f} model={r['model_price']:>7.4f} "
          f"mark={r['market_price']:>7.4f} rel_err={r['relative_error']:>6.1%} "
          f"IV={r['implied_volatility']:.3f} {flag}")

with open("options_validation_report.json", "w") as f:
    json.dump(report, f, indent=2)
print("Wrote options_validation_report.json")
