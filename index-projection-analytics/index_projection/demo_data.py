"""Seeded synthetic demo universe. All tickers, prices and returns are
invented for demonstration; nothing here is a real index or real company.
"""

from .universe import Constituent, IndexUniverse


def build_demo_universe() -> IndexUniverse:
    constituents = [
        Constituent("AAA", 100.0, 50.0, 0.80, "Technology"),
        Constituent("BBB", 200.0, 25.0, 0.90, "Financials"),
        Constituent("CCC", 50.0, 100.0, 1.00, "Health Care"),
        Constituent("DDD", 80.0, 60.0, 0.85, "Industrials"),
        Constituent("EEE", 150.0, 30.0, 0.75, "Consumer Staples"),
        Constituent("FFF", 60.0, 90.0, 0.95, "Energy"),
        Constituent("GGG", 120.0, 40.0, 0.70, "Utilities"),
        Constituent("HHH", 90.0, 55.0, 0.88, "Materials"),
    ]
    return IndexUniverse(constituents, base_level=1000.0)


DEMO_CANDIDATE = Constituent("III", 110.0, 70.0, 0.92, "Technology")

_TICKERS = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH"]

DEMO_SCENARIOS = {
    "base case (+2% broad)": {t: 0.02 for t in _TICKERS},
    "growth rally": {"AAA": 0.08, "BBB": 0.01, "CCC": 0.04, "DDD": 0.03,
                     "EEE": 0.01, "FFF": -0.02, "GGG": 0.00, "HHH": 0.02},
    "broad sell-off": {t: -0.05 for t in _TICKERS},
}
