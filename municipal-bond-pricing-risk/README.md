# Municipal Bond Pricing & Risk Engine

A local, end-to-end municipal bond pricing and risk engine built in Python
(standard library only) — a portfolio project matching municipal
fixed-income quantitative roles: pricing and risk models for municipal
bonds, bond derivatives and related products, trading-strategy research,
Python, pandas/NumPy-style analysis, and machine learning / statistical
relative-value work for a municipal bond market-making desk. It was first
built for Morgan Stanley's Fixed Income Division — Analyst or Associate,
Municipal Markets (New York) role, extended with a public-finance sector
screen for JPMorgan's Quantitative Trading & Research — Credit & Public
Finance Sales role, and extended again with leverage/funding risk and
performance attribution for Invesco's Quantitative Analyst, Municipal
Fixed Income role (Req R-15895).

**All market data is synthetic and seeded in code.** No real issuer, CUSIP,
or market data appears anywhere in this project, and nothing here was used
in production or by any real company.

## What it does

| Module | Morgan Stanley JD item |
|---|---|
| `muni_engine/curve.py` | **Tax-exempt yield curve** — bootstraps zero rates from benchmark par yields, linear interpolation, taxable-equivalent yield |
| `muni_engine/bonds.py` | **Pricing** — semiannual muni pricing, yield-to-maturity, yield-to-call, yield-to-worst (the yield traders quote) |
| `muni_engine/oas.py` | **Option-adjusted spread** — recombining binomial short-rate tree calibrated to the curve, optimal call exercise, OAS by bisection |
| `muni_engine/risk.py` | **Inventory risk** — modified duration, convexity, DV01, key-rate durations, credit-spread scenarios (P&L per 100 par) |
| `muni_engine/relative_value.py` | **Relative-value screen** — OLS regression of spread on maturity, coupon, rating and callability; CHEAP / RICH / FAIR flags |
| `muni_engine/public_finance.py` | **Public-finance sector screen** — mean spread/residual per sector (GO, water/sewer, toll road, hospital, school, housing); cheap/rich vs sector peers; ranked sales ideas with taxable-equivalent yield |
| `muni_engine/leverage.py` | **Leverage & funding risk** — tender option bond (TOB) trust: leverage ratio, funding cost incl. liquidity/remarketing fees, residual yield, distribution coverage, funding-rate shock scenarios; VMTP cost; FUNDING STRESS verdict when a +100bp floater-rate rise leaves the distribution uncovered |
| `muni_engine/performance.py` | **Performance attribution** — expected vs realised return decomposed into market/economic drivers (rates, spread, curve) and an unexplained residual; MARKET-DRIVEN vs DATA/MODEL ISSUE verdict so a data or model problem is told apart from a market move |
| `run_muni.py` | End-to-end demo: curve, callable-bond pricing, risk report, 13-bond screen; writes `muni_report.txt` / `muni_report.json` |

## How to run

```bash
pip install -r requirements.txt   # pytest only; the engine is stdlib-only
python run_muni.py                # demo: writes muni_report.txt + muni_report.json
python -m pytest -q               # 54 tests
```

Requires Python 3.12.

## Demo results (real run)

Seeded run: tax-exempt curve bootstrapped from synthetic par yields
(1y 2.21% … 10y 3.61% … 30y 4.86%). A **5% 20-year callable muni,
callable at par in 10 years, priced at 104.50**:

- YTM **4.652%**, yield-to-worst **4.438%** (the 10-year call binds — the
  premium bond's quoted yield is the call yield, not YTM)
- OAS **42.7bp** at 10% short-rate volatility
- Modified duration **12.85**, convexity **218.8**, DV01 **$0.1382** per
  100 par
- Key-rate durations: 2y 0.08, 5y 0.37, 10y 2.11, 20y 9.09, 30y 0.00 —
  risk concentrates at the 20-year point, as expected for a 20y bond
- Spread scenarios (P&L per 100 par): −100bp **+15.06**, −50bp **+7.21**,
  +50bp **−6.62**, +100bp **−12.70**, +200bp **−23.45**
- Relative-value screen over a synthetic 13-bond universe: OLS spread
  model R² **0.755**; 12 bonds screen FAIR within ±25bp, and a
  deliberately mispriced bond at +130bp spread is flagged CHEAP (test).
- Public-finance sector screen: GO mean spread **56.2bp**, hospital
  **103.0bp**, toll road **73.0bp** — sectors trade at different levels,
  so the screen is run within each sector too. Top sales idea:
  **MUNI-13** (GO, AA, 20y) at 130bp vs an 83.65bp model spread,
  **+37.6bp cheap vs its GO peers**, taxable-equivalent yield **8.57%**
  at a 37% tax bracket.
- Leverage & funding (TOB trust: 100 par of 4.5% bonds, 75 par floaters
  at 3.0% + 15bp fees): leverage **4.0x**, residual yield **8.55%**,
  distribution coverage **1.425** — but a **+100bp** rise in the floater
  rate cuts coverage to **0.925**, verdict **FUNDING STRESS**; at
  **+200bp** coverage falls to **0.425**. VMTP leg (50 par at 3.2% +
  25bp spread) costs **$1.725** (**3.45** per 100 par).
- Performance attribution (expected 1.20% vs realised 0.85%): gap
  **−0.35%**, market drivers explain **−0.25%** (rates −0.20, spread
  −0.10, curve +0.05), unexplained residual **−0.10%** — within the
  10bp tolerance, verdict **MARKET-DRIVEN**.

## Tests

33 pytest tests cover curve interpolation and bootstrapping (par bonds
reprice at 100), pricing/yield round-trips, yield-to-worst call-vs-maturity
selection, callable < bullet value, OAS repricing the market price,
duration/convexity/DV01 ranges, key-rate durations summing near total
duration, spread-scenario monotonicity, the relative-value screen
(coefficient signs, R², outlier flagged CHEAP, fit guards), and the
public-finance sector screen (sector means, sector residuals removing the
sector mean, sector vs market flags, sales-idea ranking and TEY math).
