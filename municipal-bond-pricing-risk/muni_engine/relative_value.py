"""Regression-based relative-value screen for municipal bonds.

Municipal bonds trade infrequently and differ across many structural
features, so a desk cannot compare two bonds on yield alone. This screen
fits an ordinary-least-squares model of yield spread (over the tax-exempt
curve) on observable features — maturity, coupon, credit rating, and
callability — then flags bonds whose actual spread sits far above (cheap)
or below (rich) the model prediction. OLS is solved with the normal
equations and Gaussian elimination, so the module needs no third-party
libraries.
"""

import math


def _solve_linear(a, b):
    """Gaussian elimination with partial pivoting for a small dense system."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ValueError("singular design matrix")
        m[col], m[piv] = m[piv], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


class RelativeValueScreen:
    """OLS spread model over a universe of bonds, with cheap/rich flags."""

    RATING_SCORES = {"AAA": 1, "AA": 2, "A": 3, "BBB": 4, "BB": 5, "B": 6}

    def __init__(self):
        self.coef = None
        self.feature_names = ["intercept", "maturity_years", "coupon",
                              "rating_score", "callable"]

    @staticmethod
    def features(bond_dict):
        """Feature vector for one bond record (dict with the keys below)."""
        return [1.0,
                bond_dict["maturity_years"],
                bond_dict["coupon"],
                RelativeValueScreen.RATING_SCORES[bond_dict["rating"]],
                1.0 if bond_dict.get("callable") else 0.0]

    def fit(self, bonds):
        """Fit OLS of spread_bp on features. ``bonds``: list of dicts."""
        if len(bonds) < len(self.feature_names) + 1:
            raise ValueError("need more bonds than features to fit the screen")
        x = [self.features(b) for b in bonds]
        y = [b["spread_bp"] for b in bonds]
        k = len(self.feature_names)
        xtx = [[sum(row[i] * row[j] for row in x) for j in range(k)]
               for i in range(k)]
        xty = [sum(row[i] * yy for row, yy in zip(x, y)) for i in range(k)]
        self.coef = _solve_linear(xtx, xty)
        return dict(zip(self.feature_names, self.coef))

    def predict(self, bond_dict):
        if self.coef is None:
            raise ValueError("fit the screen before predicting")
        return sum(c * f for c, f in zip(self.coef, self.features(bond_dict)))

    def screen(self, bonds, threshold_bp=25.0):
        """Flag each bond CHEAP / RICH / FAIR against the fitted model."""
        out = []
        for b in bonds:
            predicted = self.predict(b)
            residual = b["spread_bp"] - predicted
            if residual > threshold_bp:
                flag = "CHEAP"
            elif residual < -threshold_bp:
                flag = "RICH"
            else:
                flag = "FAIR"
            out.append({**b, "predicted_spread_bp": round(predicted, 2),
                        "residual_bp": round(residual, 2), "flag": flag})
        return out

    def r_squared(self, bonds):
        """In-sample R-squared of the fitted spread model."""
        y = [b["spread_bp"] for b in bonds]
        mean = sum(y) / len(y)
        ss_tot = sum((v - mean) ** 2 for v in y)
        ss_res = sum((b["spread_bp"] - self.predict(b)) ** 2 for b in bonds)
        return 1.0 - ss_res / ss_tot if ss_tot else 0.0
