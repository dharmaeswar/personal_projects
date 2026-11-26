"""Market-data ingestion, featurization, and training/evaluation pipeline.

This module is the quant-AI engineering slice of the platform: it ingests a
stream of synthetic order-book events (adds, cancels, trades), featurizes
them into the signals a price-move model consumes, and runs a time-ordered
train/evaluate cycle with a like-for-like promotion gate — the same
discipline the posting asks for: controlled, reproducible experiments,
comparisons on the same data, and a careful separation of real signal from
noise and overfitting.

Everything here is synthetic and seeded. No real market data, prices, or
order flow is used anywhere. The event generator builds in a real, known
signal — order-flow imbalance pushes the mid-price — so the trained model
can recover it, and the evaluation reports whether it actually did (model
AUC vs. a naive order-flow-rule baseline and a majority-class baseline).

Design notes (the parts the posting cares about):

- Ingestion is append-only and timestamp-ordered; featurization never looks
  ahead of the window it is scoring, and labels are computed from prices
  strictly after the feature window closes.
- The train/test split is by time, never shuffled: a model is always tested
  on market events that happened after everything it trained on. A shuffled
  split would leak the future into training and flatter the metrics.
- Every run writes a reproducibility manifest (dataset fingerprint, config
  hash, code version, seed) via ``eval_pipeline.reproducibility_manifest``,
  so two runs with identical manifests ran on identical inputs.
- Promotion uses the shared ``evaluation.promotion_gate``: the candidate is
  compared with the current production model on the same held-out set, and
  promotes only on a real improvement above a floor.
"""

import math
import random

from .evaluation import dataset_fingerprint, evaluate, promotion_gate
from .eval_pipeline import reproducibility_manifest

MARKET_FEATURES = [
    "log_return",
    "order_flow_imbalance",
    "realized_vol",
    "rel_spread",
    "trade_share",
    "cancel_ratio",
]

CODE_VERSION = "ml-training-serving-platform-1.2.0"


# ---------------------------------------------------------------------------
# Ingestion: synthetic order-book event stream
# ---------------------------------------------------------------------------

def generate_order_events(n, seed=42, start_mid=100.0):
    """Generate ``n`` synthetic order-book events, timestamp-ordered.

    Each event is a dict: seq, ts_ms, side ("bid"/"ask"), kind
    ("add"/"cancel"/"trade"), price, size. The mid-price follows a random
    walk whose drift is pushed by order-flow imbalance, so flow carries
    real (but noisy) signal about the next move — the same structure a
    price-prediction model has to learn from real order flow.

    The signal is persistent, not instantaneous: a latent flow regime
    (+1 buying pressure, 0 neutral, -1 selling pressure) lasts for many
    events, tilts both the side mix of incoming orders and the mid-price
    drift, and only flips occasionally. Past-window order-flow imbalance
    therefore predicts the next move — but only weakly, because per-event
    noise is large relative to the drift, which is exactly why the
    evaluation must compare against naive baselines instead of trusting a
    raw accuracy number.
    """
    rng = random.Random(seed)
    events = []
    mid = start_mid
    ts = 0
    regime = 0
    for seq in range(n):
        ts += rng.randint(1, 25)  # irregular arrival, milliseconds
        if rng.random() < 0.005:  # regime flips only occasionally: persistence
            regime = rng.choice([-1, 0, 1])
        p_bid = 0.5 + 0.2 * regime
        side = "bid" if rng.random() < p_bid else "ask"
        kind = rng.choices(["add", "cancel", "trade"], weights=[0.6, 0.25, 0.15])[0]
        # Order flow pushes the mid: more aggressive buy flow lifts it.
        flow_push = 0.0
        if kind == "trade":
            flow_push = 0.0004 if side == "bid" else -0.0004
        elif kind == "add":
            flow_push = 0.0001 if side == "bid" else -0.0001
        drift = 0.0003 * regime
        mid *= math.exp(rng.gauss(0.0, 0.0006) + flow_push + drift)
        spread = rng.uniform(0.01, 0.05)
        price = mid - spread / 2 if side == "bid" else mid + spread / 2
        size = rng.randint(1, 500)
        events.append(
            {
                "seq": seq,
                "ts_ms": ts,
                "side": side,
                "kind": kind,
                "price": round(price, 4),
                "size": size,
                "mid": round(mid, 4),
            }
        )
    return events


# ---------------------------------------------------------------------------
# Featurization: windowed signals + forward label (no look-ahead)
# ---------------------------------------------------------------------------

def _window_features(window_events):
    """Features for one window of events. Uses only events in the window."""
    mids = [e["mid"] for e in window_events]
    log_return = math.log(mids[-1] / mids[0]) if mids[0] > 0 else 0.0
    buy_vol = sum(e["size"] for e in window_events if e["side"] == "bid")
    sell_vol = sum(e["size"] for e in window_events if e["side"] == "ask")
    total_vol = buy_vol + sell_vol
    ofi = (buy_vol - sell_vol) / total_vol if total_vol else 0.0
    log_mids = [math.log(m) for m in mids]
    changes = [b - a for a, b in zip(log_mids, log_mids[1:])]
    mean_change = sum(changes) / len(changes) if changes else 0.0
    var = sum((c - mean_change) ** 2 for c in changes) / len(changes) if changes else 0.0
    realized_vol = math.sqrt(var)
    spreads = [
        (e["price"] - e["mid"]) / e["mid"] if e["side"] == "ask"
        else (e["mid"] - e["price"]) / e["mid"]
        for e in window_events
    ]
    rel_spread = sum(spreads) / len(spreads) if spreads else 0.0
    trades = sum(1 for e in window_events if e["kind"] == "trade")
    cancels = sum(1 for e in window_events if e["kind"] == "cancel")
    trade_share = trades / len(window_events) if window_events else 0.0
    cancel_ratio = cancels / len(window_events) if window_events else 0.0
    return {
        "log_return": round(log_return, 6),
        "order_flow_imbalance": round(ofi, 4),
        "realized_vol": round(realized_vol, 6),
        "rel_spread": round(rel_spread, 6),
        "trade_share": round(trade_share, 4),
        "cancel_ratio": round(cancel_ratio, 4),
    }


def featurize(events, window=50, horizon=10, stride=10):
    """Turn an event stream into (features, label, ts_ms) rows.

    Features come from the ``window`` events ending at index ``i``; the
    label is 1 when the mid-price ``horizon`` events later is above the
    mid at ``i`` — strictly future data, so no label leakage. Rows are
    emitted every ``stride`` events. Returns rows in time order.
    """
    rows = []
    n = len(events)
    for i in range(window - 1, n - horizon, stride):
        window_events = events[i - window + 1 : i + 1]
        features = _window_features(window_events)
        future_mid = events[i + horizon]["mid"]
        label = 1 if future_mid > events[i]["mid"] else 0
        rows.append((features, label, events[i]["ts_ms"]))
    return rows


def time_split(rows, train_frac=0.7):
    """Split rows by time: train is the earlier slice, test the later one.

    Raises ValueError if the split would mix time order (it cannot for
    rows produced by ``featurize``, which are time-ordered; the check is
    the guard that keeps a shuffled input from silently leaking).
    """
    if not rows:
        return [], []
    cut = max(1, int(len(rows) * train_frac))
    train_rows, test_rows = rows[:cut], rows[cut:]
    if test_rows and train_rows and test_rows[0][2] <= train_rows[-1][2]:
        raise ValueError("time split would mix time order: test starts before train ends")
    return train_rows, test_rows


# ---------------------------------------------------------------------------
# Model: plain-Python logistic regression over the market features
# ---------------------------------------------------------------------------

def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x)) if x >= -700 else 0.0


class MarketModel:
    """Logistic regression over MARKET_FEATURES, with scaling baked in."""

    def __init__(self, weights, bias, means, stds, features=None):
        self.weights = weights
        self.bias = bias
        self.means = means
        self.stds = stds
        self.features = features or list(MARKET_FEATURES)

    def predict_proba(self, features):
        x = [(features[f] - m) / s for f, m, s in zip(self.features, self.means, self.stds)]
        z = self.bias + sum(w * v for w, v in zip(self.weights, x))
        return _sigmoid(z)

    def predict(self, features, threshold=0.5):
        return 1 if self.predict_proba(features) >= threshold else 0

    def to_dict(self):
        return {
            "weights": self.weights,
            "bias": self.bias,
            "means": self.means,
            "stds": self.stds,
            "features": self.features,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["weights"], d["bias"], d["means"], d["stds"], d["features"])


def train_market_model(rows, epochs=300, lr=0.1, seed=7, features=None):
    """Train a MarketModel on (features, label, ts) rows. Returns the model.

    ``features`` selects the feature subset to train on (default: all of
    MARKET_FEATURES). The pipeline uses it to build the production model
    it gates against: a model trained on order-flow imbalance alone, so
    the gate measures what the full feature set adds over the naive signal.
    """
    features = features or list(MARKET_FEATURES)
    train_rows = [(f, y) for f, y, _ in rows]
    X = [[float(r[0][f]) for f in features] for r in train_rows]
    y = [r[1] for r in train_rows]
    means = [sum(col) / len(col) for col in zip(*X)]
    stds = []
    for c in range(len(features)):
        var = sum((row[c] - means[c]) ** 2 for row in X) / len(X)
        stds.append(math.sqrt(var) or 1.0)
    Xs = [[(row[c] - means[c]) / stds[c] for c in range(len(features))] for row in X]
    rng = random.Random(seed)
    weights = [rng.uniform(-0.1, 0.1) for _ in features]
    bias = 0.0
    n = len(Xs)
    for _ in range(epochs):
        grad_w = [0.0] * len(features)
        grad_b = 0.0
        for xi, yi in zip(Xs, y):
            p = _sigmoid(bias + sum(w * v for w, v in zip(weights, xi)))
            err = p - yi
            for j in range(len(weights)):
                grad_w[j] += err * xi[j]
            grad_b += err
        weights = [w - lr * g / n for w, g in zip(weights, grad_w)]
        bias -= lr * grad_b / n
    return MarketModel(weights, bias, means, stds, features=features)


# ---------------------------------------------------------------------------
# Baselines: is the model finding real signal, or noise?
# ---------------------------------------------------------------------------

def baseline_metrics(rows):
    """Majority-class and naive order-flow-rule baselines on the same rows.

    The OFI rule predicts "up" whenever order-flow imbalance is positive.
    A trained model that cannot beat both baselines on AUC has found no
    real signal — it is fitting noise, and must not promote.
    """
    if not rows:
        return {"majority_accuracy": 0.0, "ofi_rule_accuracy": 0.0, "ofi_rule_auc": 0.5}
    n_up = sum(y for _, y, _ in rows)
    majority = max(n_up, len(rows) - n_up) / len(rows)
    ofi_correct = sum(
        1 for f, y, _ in rows if (1 if f["order_flow_imbalance"] > 0 else 0) == y
    )
    # AUC of the OFI score itself, pairwise.
    pos = [f["order_flow_imbalance"] for f, y, _ in rows if y == 1]
    neg = [f["order_flow_imbalance"] for f, y, _ in rows if y == 0]
    if not pos or not neg:
        ofi_auc = 0.5
    else:
        wins = sum(1 for p in pos for q in neg if p > q) + 0.5 * sum(
            1 for p in pos for q in neg if p == q
        )
        ofi_auc = wins / (len(pos) * len(neg))
    return {
        "majority_accuracy": round(majority, 4),
        "ofi_rule_accuracy": round(ofi_correct / len(rows), 4),
        "ofi_rule_auc": round(ofi_auc, 4),
    }


# ---------------------------------------------------------------------------
# End-to-end run: ingest -> featurize -> time split -> train -> gate
# ---------------------------------------------------------------------------

def run_market_pipeline(n_events=20000, window=50, horizon=10, stride=10,
                        seed=42, epochs=300, min_improvement=0.005):
    """Run the full pipeline and return a report dict.

    The candidate trains for ``epochs``; the production model it is gated
    against trains for the same epochs but on order-flow imbalance alone,
    so the gate measures what the full feature set adds over the naive
    signal, on the same held-out set, like for like.
    """
    config = {
        "n_events": n_events, "window": window, "horizon": horizon,
        "stride": stride, "seed": seed, "epochs": epochs,
    }
    events = generate_order_events(n_events, seed=seed)
    rows = featurize(events, window=window, horizon=horizon, stride=stride)
    train_rows, test_rows = time_split(rows)
    candidate = train_market_model(train_rows, epochs=epochs, seed=seed)
    production = train_market_model(train_rows, epochs=epochs, seed=seed,
                                    features=["order_flow_imbalance"])
    eval_rows = [(f, y) for f, y, _ in test_rows]
    candidate_metrics = evaluate(candidate, eval_rows)
    gate = promotion_gate(candidate, production, eval_rows,
                          primary="auc", min_improvement=min_improvement,
                          floors={"accuracy": 0.50})
    baselines = baseline_metrics(test_rows)
    manifest = reproducibility_manifest(
        "synthetic-order-events", eval_rows, config, seed,
        model_version="market-candidate-1", code_version=CODE_VERSION,
    )
    manifest["dataset_fingerprint"] = dataset_fingerprint(eval_rows)
    return {
        "n_events": len(events),
        "n_rows": len(rows),
        "n_train": len(train_rows),
        "n_test": len(test_rows),
        "candidate_metrics": candidate_metrics,
        "baselines": baselines,
        "gate": gate,
        "manifest": manifest,
        "signal_found": candidate_metrics["auc"] > baselines["ofi_rule_auc"],
    }
