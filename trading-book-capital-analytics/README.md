# Trading-Book Capital Analytics

Cross-asset quantitative models for measuring and optimising regulatory
capital across a global trading book — the same problem Citi's Capital
Analytics team works on: help traders see the capital impact of their
activity in real time, price capital-efficiently, and use the balance
sheet better.

Built for the Citi Markets Quantitative Analyst – Capital Analytics (AVP)
application (Nov 27, 2026). All data is synthetic and seeded; no real
market data, no real counterparties. Standard library only for the math.

## What it does

- **Exposure at default (EAD)** — a simplified SA-CCR-style method:
  `EAD = 1.4 × (Replacement Cost + multiplier × AddOn)`, with
  same-asset-class netting (offsetting notionals cancel), a maturity
  factor capped at one year, and the PFE multiplier for
  over-collateralised netting sets.
- **Risk-weighted assets and capital** — `RWA = EAD × risk weight`
  (20% rates/FX, 100% equity/credit/commodity in this simplified
  standardised-style mapping), `capital = 8% × RWA`. EAD is split
  across trades by add-on share so each trade carries its part of the
  netted exposure.
- **Marginal capital and return on capital** — the incremental capital a
  new trade consumes, and expected P&L per dollar of that capital.
  This is the number a trader needs to price a trade capital-efficiently.
- **Capital-budget optimisation** — greedy allocation of a capital
  budget across candidate trades, ranked by return on marginal capital.
- **Capital-efficient structuring** — find the hedge that cuts book
  capital the most per dollar of P&L given up.

## Layout

```
capital/
  trades.py        synthetic 30-trade cross-asset book (rates, FX, equity,
                   credit, commodities), seeded and deterministic
  exposure.py      SA-CCR-style EAD, netting, replacement cost, multiplier
  capital.py       RWA, capital (8%), marginal capital, return on capital
  optimisation.py  capital-budget allocation, best-hedge search
  validation.py    12 invariant checks (identities, not fitted numbers)
  var_risk.py      VaR / ES, P&L explain, factor attribution, scenarios,
                   VaR backtest (Millennium Quant Risk Researcher extension)
run_capital.py     demo runner: book summary, desk capital, optimisation
tests/
  test_capital.py  13 pytest tests
  test_var_risk.py 9 pytest tests
```

## VaR, P&L explain and scenarios (new, Nov 2026 — built for a Millennium Quant Risk Researcher role)

The JD's work is monitoring and explaining P&L, performance and risk
for quantitative-strategy portfolios, and building simulation models
for risk measurement. `capital/var_risk.py` adds exactly that on the
same synthetic book:

- **Simulated factor history** — 252 seeded days of rates / FX /
  equity / credit / commodity factor returns from a one-factor
  correlation model (rho 0.3), with per-factor daily vols.
- **Historical VaR / expected shortfall** — 95% and 99% VaR and ES
  from the simulated daily book P&L (trade P&L = notional x an
  illustrative instrument sensitivity x factor return, plus carry
  and a small idiosyncratic term).
- **P&L explain** — one day's book P&L split into carry, per-factor
  contributions and an idiosyncratic residual; the parts sum to the
  total by construction (tested).
- **Factor attribution** — each factor's share of absolute daily P&L.
- **Scenario analysis** — rates +100bp, equities −10%, credit
  spreads +200bp, commodities −15%, USD +5%, and a combined stress.
- **VaR backtest** — rolling 60-day historical VaR, breach count vs
  the expected 5% rate.

Demo output (real run, Nov 27, 2026):

```
VaR on 252 simulated days: 95% VaR $765,902   99% VaR $1,087,658   95% ES $944,559
mean daily P&L $-20,887   daily vol $460,657
P&L attribution by factor: fx 30.5%, credit 26.4%, commodity 20.2%, equity 18.9%, rates 4.0%
scenario P&L: Commodities -15% $-3,939,725; Combined stress $-2,100,456; USD +5% $1,577,581
VaR backtest (95%, 60-day window): 12 breaches in 192 days (6.2% vs 5.0% expected)
tests: 22 passed
```

Honest limit: the factor returns are simulated, the sensitivities
are illustrative delta proxies (not calibrated betas), and the VaR
is a historical simulation on those simulated returns — the analytics
workflow is the point, not a production risk number. The book is net
short equities in the seeded draw, so the equities −10% scenario
shows a small gain; the combined stress is still a $2.1m loss,
driven by the long commodities sleeve.

## Run it

```bash
python run_capital.py
python -m pytest -q
```

## Demo output (real run, Nov 27, 2026)

```
book: 30 synthetic cross-asset trades, gross notional $653.0m
total EAD: $7.50m   RWA: $6.46m   capital (8%): $0.52m

EAD / capital by desk:
  Commodities  EAD $    5.71m   capital $  0.46m
  Credit       EAD $    0.43m   capital $  0.03m
  Equities     EAD $    0.42m   capital $  0.03m
  FX           EAD $    1.47m   capital $  0.02m
  Rates        EAD $    0.00m   capital $  0.00m

capital budget $2,000,000: chose 2 of 10 candidates, used $49,693,
expected P&L $659,456, left $1,950,307

hedge T027 (Commodities future $7.8m): saves $118,799 of capital at a
P&L cost of $2,000 (efficiency 59.40x)

validation checks: 14 PASS, 0 FAIL
tests: 13 passed
```

(The exact numbers above are from the seeded demo run; re-running the
commands reproduces them. Note the Rates desk shows ~$0 EAD: its six
swaps nearly cancel — $281.4m gross notional but only $7.8m net — so
same-class netting wipes out almost all of its add-on. That is the
model working as designed, not a missing desk.)

## Honest limits

- The SA-CCR and standardised risk weights here are **simplified
  teaching models**: real SA-CCR uses hedging sets, supervisory
  correlations and maturity buckets, and real standardised weights
  depend on counterparty type, rating and maturity. The simplifications
  are labelled in the code wherever they matter.
- The book, prices and P&L are synthetic. The project shows the
  modelling, the code structure and the validation discipline — it is
  not a production capital calculation.
