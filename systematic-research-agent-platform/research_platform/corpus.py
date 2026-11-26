"""Seeded corpora for the knowledge layer.

All documents are synthetic and fictional, written for this demo: research
notes about systematic signals, Python research-code snippets, and dataset
summaries with factor statistics. No real Man Group research, code, or
market data is used. Numbers are invented seed values, not real results.
"""

DOCUMENTS = [
    {
        "id": "RN-MOM-01",
        "kind": "research",
        "title": "Time-series momentum in futures: 252-day lookback",
        "text": (
            "Time-series momentum takes the sign of the trailing 252-day return as the "
            "position. The signal is scaled by its own trailing volatility so that calm "
            "and stressed regimes carry similar risk. In our seeded backtest the "
            "momentum sleeve returned 6.2 percent annualised with 11.4 percent "
            "volatility, a Sharpe ratio of 0.54. Momentum underperforms during sharp "
            "reversals, when the trailing return flips sign after the position is set. "
            "We therefore cap the sleeve at 40 percent of book risk and require the "
            "signal to survive a 5-day execution delay before it is trusted."
        ),
    },
    {
        "id": "RN-CARRY-01",
        "kind": "research",
        "title": "FX carry: rate differentials and crash risk",
        "text": (
            "FX carry goes long the higher-yielding currency of a pair, with position "
            "size proportional to the rate differential. In the seeded sample the carry "
            "sleeve returned 4.8 percent annualised with 9.1 percent volatility, a "
            "Sharpe ratio of 0.53. Carry earns a steady premium most of the time and "
            "loses abruptly in risk-off episodes, so the desk pairs it with a "
            "volatility filter that cuts exposure when realised volatility doubles. "
            "Funding costs are charged at the short rate of the funding currency."
        ),
    },
    {
        "id": "RN-VOL-01",
        "kind": "research",
        "title": "Volatility targeting and risk parity sizing",
        "text": (
            "Volatility targeting scales each position so the portfolio runs at a "
            "constant 10 percent annualised volatility. When realised volatility "
            "rises above target, positions are scaled down proportionally; when it "
            "falls, they are scaled up, subject to a leverage cap of 2.0 times. "
            "The seeded portfolio held realised volatility at 10.3 percent against "
            "the 10 percent target. Rebalancing is weekly, and turnover is capped "
            "at 15 percent of the book per week to keep transaction costs bounded."
        ),
    },
    {
        "id": "RN-MREV-01",
        "kind": "research",
        "title": "Short-horizon mean reversion as a diversifier",
        "text": (
            "Short-horizon mean reversion fades moves away from the 20-day average. "
            "It is kept as a small sleeve, at most 15 percent of book risk, because "
            "its edge decays fast and it loses during trending markets. In the seeded "
            "sample the sleeve returned 2.1 percent annualised with 7.6 percent "
            "volatility, a Sharpe ratio of 0.28. Its correlation with the momentum "
            "sleeve is negative 0.31, which is why it is held despite the lower "
            "standalone Sharpe ratio. Execution delay beyond 2 days removes the edge."
        ),
    },
    {
        "id": "CODE-MOM-01",
        "kind": "code",
        "title": "momentum_signal.py — time-series momentum signal",
        "text": (
            "def momentum_signal(prices, lookback=252):\n"
            "    returns = prices.pct_change(lookback)\n"
            "    vol = prices.pct_change().rolling(60).std() * (252 ** 0.5)\n"
            "    scaled = returns / vol.replace(0, float('nan'))\n"
            "    return scaled.apply(lambda x: 1 if x > 0 else -1)\n"
            "The function takes a price series and a 252-day lookback, computes the "
            "trailing return, scales it by 60-day realised volatility, and returns "
            "plus one for a long signal and minus one for a short signal. Missing "
            "volatility values are dropped before the sign is taken, so no position "
            "is opened on an undefined scale."
        ),
    },
    {
        "id": "CODE-ZSCORE-01",
        "kind": "code",
        "title": "zscore.py — rolling z-score for mean reversion",
        "text": (
            "def zscore(prices, window=20):\n"
            "    mean = prices.rolling(window).mean()\n"
            "    std = prices.rolling(window).std()\n"
            "    return (prices - mean) / std.replace(0, float('nan'))\n"
            "The function returns the rolling 20-day z-score of a price series. "
            "A z-score above 2.0 is treated as overbought and below minus 2.0 as "
            "oversold. The mean-reversion sleeve only trades when the absolute "
            "z-score exceeds 1.5, which keeps turnover low and avoids trading noise."
        ),
    },
    {
        "id": "DATA-MOM-01",
        "kind": "data",
        "title": "Dataset: momentum factor summary statistics",
        "text": (
            "Momentum factor, 252-day lookback, seeded daily series of 1,260 "
            "observations. Annualised return 6.2 percent. Annualised volatility "
            "11.4 percent. Sharpe ratio 0.54. Maximum drawdown 18.7 percent. "
            "Correlation with the carry factor 0.12. Win rate 54 percent of months. "
            "The series is synthetic and seeded for this demo; it is not real market data."
        ),
    },
    {
        "id": "DATA-CARRY-01",
        "kind": "data",
        "title": "Dataset: FX carry factor summary statistics",
        "text": (
            "FX carry factor, seeded daily series of 1,260 observations. Annualised "
            "return 4.8 percent. Annualised volatility 9.1 percent. Sharpe ratio "
            "0.53. Maximum drawdown 22.4 percent. Correlation with the momentum "
            "factor 0.12. Win rate 61 percent of months. The series is synthetic "
            "and seeded for this demo; it is not real market data."
        ),
    },
    {
        "id": "DATA-VOL-01",
        "kind": "data",
        "title": "Dataset: volatility-targeted portfolio summary",
        "text": (
            "Volatility-targeted portfolio, target 10 percent annualised volatility. "
            "Realised volatility 10.3 percent. Leverage cap 2.0 times. Weekly "
            "rebalancing, turnover cap 15 percent of book per week. Seeded sample "
            "of 1,260 observations. The figures are synthetic and seeded for this "
            "demo; they are not real portfolio results."
        ),
    },
]


def get_documents(kind=None):
    """All seeded documents, optionally filtered by kind."""
    if kind is None:
        return list(DOCUMENTS)
    return [d for d in DOCUMENTS if d["kind"] == kind]


def get_document(doc_id):
    """One document by id, or None."""
    for doc in DOCUMENTS:
        if doc["id"] == doc_id:
            return doc
    return None
