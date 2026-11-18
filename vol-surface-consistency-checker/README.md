# Vol-Surface Consistency Checker

Batch arbitrage and consistency checks for implied-volatility surfaces.
Point it at a surface file and it flags inconsistent quotes and stale
inputs **before calibration**, replacing the manual, by-hand surface
checks analysts used to run quote by quote.

Built with pure Python + NumPy: Black-Scholes pricing, an implied-vol
solver (Newton with a bisection fallback), and a small set of
no-arbitrage checks with fast alerts on failure.

## The checks

| Check | What it verifies |
|---|---|
| **Calendar arbitrage** | For a fixed strike, total implied variance `w(T) = sigma^2 * T` is non-decreasing in expiry `T`. A decrease would let a calendar spread be locked in at a negative price. |
| **Butterfly arbitrage** | For a fixed expiry, call prices are convex in strike — equivalently the implied risk-neutral density (second strike-difference of call prices) is non-negative. Uses the slope form of convexity, so unequally spaced strikes are handled. |
| **Strike monotonicity** | For a fixed expiry, call prices are non-increasing in strike. |
| **Stale quotes** | Each quote's timestamp is compared with the newest timestamp in the file; quotes older than a configurable maximum age (default 24h) are flagged, so a dead feed is caught before its quotes reach a calibration. |
| **RMS smile error** | Per expiry, a quadratic smile `sigma(k) = a + b*k + c*k^2` is fitted in log-moneyness `k = log(K/F)` and the root-mean-square residual of the quoted vols is reported. Large residuals mark quotes sitting off the smooth surface. |

Every failed check emits an **alert record immediately** (JSON Lines,
to a file and/or the console) — a broken surface reaches the desk as it
is found, not after the batch finishes.

## Quick start

```bash
pip install -r requirements.txt

# Run over the bundled sample surface
python -m vol_surface_checker data/sample_surface.csv \
    --max-age-hours 24 \
    --report violations.json \
    --alerts alerts.jsonl

# or equivalently
python run_checks.py data/sample_surface.csv --report violations.json
```

Exit code is `1` when any violation is found, `0` when the surface is
clean — so the checker drops straight into a pre-calibration pipeline
step or CI job.

## Input format

One option quote per row:

```csv
timestamp,expiry,strike,spot,rate,option_type,market_price,implied_vol
2024-02-15T09:30:00,0.25,80,100,0.03,call,21.956126,0.427636
```

* `timestamp` — ISO-8601 quote time
* `expiry` — time to expiry in years
* `strike`, `spot` — strike and spot of the underlying
* `rate` — continuously compounded risk-free rate
* `option_type` — `call` or `put`
* `market_price` — quoted option price
* `implied_vol` — quoted implied volatility (annualised)

## Sample data

`data/sample_surface.csv` holds 37 quotes (spot 100, strikes 80–120,
expiries 0.25–2.0y) generated from a total-variance model
`w(k, T) = (0.04 + 0.02T)(1 + 0.3k^2)` that is arbitrage-free by
construction — with three defects planted on purpose:

1. a **calendar violation** (lone T=0.75 quote at strike 100 whose total
   variance falls below the T=0.5 value),
2. a **butterfly violation** (strike 100, T=2.0 price bumped off the
   convex curve),
3. a **stale quote** (strike 120, T=2.0 timestamped 10 days behind the
   rest of the file).

Regenerate it with `python tools/generate_sample_surface.py` (the
generator asserts the clean surface passes and exactly the three
planted defects are flagged).

## Example output

```text
$ python -m vol_surface_checker data/sample_surface.csv --report violations.json --alerts alerts.jsonl
ALERT {"alert": "surface_check_failed", "check": "calendar_arbitrage", "expiry": 0.75, "strike": 100.0, ...}
ALERT {"alert": "surface_check_failed", "check": "butterfly_arbitrage", "expiry": 2.0, "strike": 100.0, ...}
ALERT {"alert": "surface_check_failed", "check": "stale_quote", "expiry": 2.0, "strike": 120.0, ...}
Loaded 37 quotes from data/sample_surface.csv
Checks run: calendar_arbitrage, butterfly_arbitrage, strike_monotonicity, stale_quote (+ RMS smile error per expiry)
Result: FAIL -- 3 violation(s):
  calendar_arbitrage: 1
  butterfly_arbitrage: 1
  stale_quote: 1
RMS smile error by expiry (vol points):
  T=0.25: 0.0000
  T=0.5: 0.0000
  T=0.75: 0.0000
  T=1: 0.0000
  T=2: 0.0065
Violations report written to violations.json
3 alert record(s) written to alerts.jsonl
```

## Project layout

```text
vol_surface_checker/
    black_scholes.py   # BS pricing, vega, implied-vol solver, total variance
    surface.py         # CSV loading and the Quote/Surface model
    checks.py          # calendar / butterfly / monotonicity / stale / RMS smile
    alerts.py          # AlertSink: JSON Lines alert records, emitted on failure
    cli.py             # argument parsing, summary printing, report writing
data/
    sample_surface.csv # sample surface with three planted defects
tools/
    generate_sample_surface.py
tests/                 # pytest suite (pricing, solver, each check, end-to-end)
run_checks.py          # convenience entry point
```

## Tests

```bash
python -m pytest tests/ -q
```

The suite covers the implied-vol round trip (calls and puts, several
strikes and vols), no-arbitrage bound rejection, each check passing on
a clean surface and failing on a tampered one, RMS smile error on an
exact quadratic smile, stale-quote detection, and an end-to-end CLI run
over the sample file.
