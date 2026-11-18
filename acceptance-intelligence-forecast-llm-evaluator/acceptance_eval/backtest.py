"""Walk-forward backtesting with expanding windows."""

from .forecast import mae, rmse, mape


def walk_forward(values, model_fn, horizon=7, folds=6, step=7):
    """Fit on an expanding window, forecast `horizon` steps, roll forward.

    model_fn(history) -> list of `horizon` predictions.
    Returns a dict with per-fold metrics and aggregates.
    """
    if horizon < 1 or folds < 1 or step < 1:
        raise ValueError("horizon, folds and step must be >= 1")
    min_train = len(values) - folds * step - horizon + 1
    if min_train < 14:
        raise ValueError("series too short for the requested folds")
    fold_results = []
    start = min_train
    for f in range(folds):
        train_end = start + f * step
        train = values[:train_end]
        actual = values[train_end:train_end + horizon]
        if len(actual) < horizon:
            break
        pred = model_fn(train)
        if len(pred) != horizon:
            raise ValueError("model_fn must return exactly `horizon` values")
        fold_results.append({
            "fold": f + 1,
            "train_end": train_end,
            "mae": mae(actual, pred),
            "rmse": rmse(actual, pred),
            "mape": mape(actual, pred),
        })
    if not fold_results:
        raise ValueError("no folds produced")
    return {
        "folds": fold_results,
        "mean_mae": sum(f["mae"] for f in fold_results) / len(fold_results),
        "mean_rmse": sum(f["rmse"] for f in fold_results) / len(fold_results),
        "mean_mape": sum(f["mape"] for f in fold_results) / len(fold_results),
        "worst_mae": max(f["mae"] for f in fold_results),
    }
