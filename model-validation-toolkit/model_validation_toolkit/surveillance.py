"""Pricing-model surveillance: GARCH volatility, yield-curve PCA, rolling-window
diagnostics, out-of-sample backtests, and structural-break (CUSUM) checks.

Pure standard library. All functions take plain sequences of floats and return
plain dicts/lists, so results are easy to log into a validation document.
"""
import math
from typing import Dict, List, Sequence


# ---------------------------------------------------------------- GARCH(1,1)
def _garch_loglik(returns: Sequence[float], omega: float, alpha: float,
                  beta: float) -> float:
    """Gaussian log-likelihood of returns under a GARCH(1,1) variance recursion."""
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / n or 1e-12
    ll = 0.0
    for r in returns:
        var = omega + alpha * (r - mean) ** 2 + beta * var
        var = max(var, 1e-12)
        ll += -0.5 * (math.log(2 * math.pi * var) + (r - mean) ** 2 / var)
    return ll


def garch11_fit(returns: Sequence[float]) -> Dict[str, float]:
    """Fit GARCH(1,1) by grid search over (alpha, beta), maximising the Gaussian
    log-likelihood. omega is set from the unconditional variance so the model is
    variance-targeting: omega = long-run variance * (1 - alpha - beta).

    Returns omega, alpha, beta, long-run variance and the log-likelihood.
    """
    returns = [float(r) for r in returns]
    if len(returns) < 20:
        raise ValueError("need at least 20 returns to fit GARCH(1,1)")
    mean = sum(returns) / len(returns)
    lrv = sum((r - mean) ** 2 for r in returns) / len(returns)
    if lrv <= 0:
        raise ValueError("returns have zero variance")
    best = None
    for alpha in (0.02, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20):
        for beta in (0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92):
            if alpha + beta >= 0.99:
                continue
            omega = lrv * (1.0 - alpha - beta)
            ll = _garch_loglik(returns, omega, alpha, beta)
            if best is None or ll > best["log_likelihood"]:
                best = {"omega": omega, "alpha": alpha, "beta": beta,
                        "long_run_variance": lrv, "log_likelihood": ll}
    return best


def garch11_forecast(params: Dict[str, float], returns: Sequence[float],
                     horizon: int = 5) -> List[float]:
    """Forecast conditional variance h steps ahead from the last observed return.
    Returns a list of forecast variances (length = horizon)."""
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    returns = [float(r) for r in returns]
    if not returns:
        raise ValueError("returns must be non-empty")
    mean = sum(returns) / len(returns)
    var = params["long_run_variance"]
    for r in returns:
        var = (params["omega"] + params["alpha"] * (r - mean) ** 2
               + params["beta"] * var)
    out = []
    for _ in range(horizon):
        var = params["omega"] + (params["alpha"] + params["beta"]) * var
        out.append(var)
    return out


# ------------------------------------------------------- Yield-curve PCA
def _jacobi_eigh(matrix: List[List[float]]) -> (List[float], List[List[float]]):
    """Eigen-decomposition of a symmetric matrix by cyclic Jacobi rotations.
    Returns (eigenvalues, eigenvectors as columns) in descending order."""
    n = len(matrix)
    a = [row[:] for row in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(100):
        off = math.sqrt(sum(a[i][j] ** 2 for i in range(n) for j in range(n)
                            if i != j))
        if off < 1e-12:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-14:
                    continue
                theta = 0.5 * math.atan2(2 * a[p][q], a[q][q] - a[p][p])
                c, s = math.cos(theta), math.sin(theta)
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    order = sorted(range(n), key=lambda i: -a[i][i])
    vals = [a[i][i] for i in order]
    vecs = [[v[row][i] for row in range(n)] for i in order]
    return vals, vecs


def yield_curve_pca(curves: Sequence[Sequence[float]]) -> Dict[str, object]:
    """PCA on a yield-curve panel: rows are observation dates, columns are tenors.

    Returns eigenvalues, explained-variance ratios, loadings (one per component,
    aligned with the tenor columns) and the first-component scores.
    """
    rows = [[float(x) for x in row] for row in curves]
    if len(rows) < 3:
        raise ValueError("need at least 3 curve observations")
    ncols = len(rows[0])
    if any(len(r) != ncols for r in rows):
        raise ValueError("all curves must have the same number of tenors")
    if ncols < 2:
        raise ValueError("need at least 2 tenors")
    means = [sum(r[j] for r in rows) / len(rows) for j in range(ncols)]
    centered = [[r[j] - means[j] for j in range(ncols)] for r in rows]
    n = len(rows)
    cov = [[sum(centered[t][i] * centered[t][j] for t in range(n)) / (n - 1)
            for j in range(ncols)] for i in range(ncols)]
    vals, vecs = _jacobi_eigh(cov)
    total = sum(vals) or 1e-12
    ratios = [max(v, 0.0) / total for v in vals]
    scores = [sum(centered[t][j] * vecs[0][j] for j in range(ncols))
              for t in range(n)]
    return {"eigenvalues": vals, "explained_variance_ratio": ratios,
            "loadings": vecs, "first_component_scores": scores,
            "tenor_means": means}


# --------------------------------------------- Rolling-window diagnostics
def rolling_window_diagnostics(series: Sequence[float],
                               window: int) -> List[Dict[str, float]]:
    """Rolling mean / std / range plus a z-score for the window's last value.
    One dict per window, keyed by the index of the window's last observation."""
    series = [float(x) for x in series]
    if window < 2:
        raise ValueError("window must be at least 2")
    if len(series) < window:
        raise ValueError("series shorter than window")
    out = []
    for end in range(window - 1, len(series)):
        w = series[end - window + 1:end + 1]
        mean = sum(w) / window
        var = sum((x - mean) ** 2 for x in w) / window
        std = math.sqrt(var)
        z = (series[end] - mean) / std if std > 0 else 0.0
        out.append({"index": end, "mean": mean, "std": std,
                    "min": min(w), "max": max(w), "z_score": z})
    return out


# ------------------------------------------------- Out-of-sample backtest
def out_of_sample_backtest(actual: Sequence[float], predicted: Sequence[float],
                           threshold: float) -> Dict[str, float]:
    """Backtest on a holdout sample: residuals, RMSE/MAE/bias, and how often the
    absolute residual breaches the monitoring threshold."""
    actual = [float(x) for x in actual]
    predicted = [float(x) for x in predicted]
    if len(actual) != len(predicted) or not actual:
        raise ValueError("actual and predicted must be non-empty and equal length")
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    residuals = [a - p for a, p in zip(actual, predicted)]
    n = len(residuals)
    breaches = sum(1 for r in residuals if abs(r) > threshold)
    return {"n": n, "bias": sum(residuals) / n,
            "mae": sum(abs(r) for r in residuals) / n,
            "rmse": math.sqrt(sum(r * r for r in residuals) / n),
            "max_abs_residual": max(abs(r) for r in residuals),
            "breaches": breaches, "breach_rate": breaches / n}


# ------------------------------------------------- Structural-break check
def cusum_break_check(residuals: Sequence[float],
                      threshold: float = 3.0) -> Dict[str, object]:
    """CUSUM-style structural-break check on standardised residuals: cumulative
    sums of (residual / residual std). Flags a break when the largest absolute
    cumulative sum exceeds threshold * sqrt(n)."""
    residuals = [float(r) for r in residuals]
    if len(residuals) < 5:
        raise ValueError("need at least 5 residuals")
    mean = sum(residuals) / len(residuals)
    var = sum((r - mean) ** 2 for r in residuals) / len(residuals)
    std = math.sqrt(var)
    if std == 0:
        return {"max_abs_cusum": 0.0, "break_index": -1, "break_flag": False,
                "limit": threshold * math.sqrt(len(residuals))}
    cusum = 0.0
    max_abs, max_idx = 0.0, -1
    for i, r in enumerate(residuals):
        cusum += (r - mean) / std
        if abs(cusum) > max_abs:
            max_abs, max_idx = abs(cusum), i
    limit = threshold * math.sqrt(len(residuals))
    return {"max_abs_cusum": max_abs, "break_index": max_idx,
            "break_flag": max_abs > limit, "limit": limit}
