import numpy as np

from dl_credit.mlp import MLPClassifier


def _toy(n=400, seed=1):
    rng = np.random.default_rng(seed)
    X = rng.normal(0, 1, (n, 4))
    logit = 2.0 * X[:, 0] - 1.5 * X[:, 1] + 0.5 * X[:, 2]
    p = 1 / (1 + np.exp(-logit))
    y = (rng.random(n) < p).astype(int)
    return X, y


def test_mlp_learns_separable_signal():
    X, y = _toy()
    model = MLPClassifier(hidden=(8, 4), lr=0.1, epochs=120, patience=15)
    model.fit(X, y)
    proba = model.predict_proba(X)
    assert proba.shape == (len(y),)
    assert ((proba >= 0) & (proba <= 1)).all()
    acc = np.mean(model.predict(X) == y)
    assert acc > 0.75


def test_mlp_loss_decreases():
    X, y = _toy()
    model = MLPClassifier(hidden=(8, 4), lr=0.1, epochs=60, patience=60)
    model.fit(X, y)
    assert model.train_loss_[-1] < model.train_loss_[0]
    assert model.n_epochs_run_ == 60


def test_mlp_early_stopping_stops_before_max_epochs():
    X, y = _toy()
    Xtr, Xva = X[:300], X[300:]
    ytr, yva = y[:300], y[300:]
    model = MLPClassifier(hidden=(8, 4), lr=0.05, epochs=300, patience=5)
    model.fit(Xtr, ytr, Xva, yva)
    assert model.n_epochs_run_ < 300
    assert len(model.val_loss_) == model.n_epochs_run_


def test_mlp_same_seed_reproduces():
    X, y = _toy()
    m1 = MLPClassifier(hidden=(8, 4), lr=0.1, epochs=40, patience=40)
    m2 = MLPClassifier(hidden=(8, 4), lr=0.1, epochs=40, patience=40)
    m1.fit(X, y)
    m2.fit(X, y)
    assert np.allclose(m1.predict_proba(X), m2.predict_proba(X))


def test_mlp_predict_binary():
    X, y = _toy()
    model = MLPClassifier(hidden=(8, 4), lr=0.1, epochs=30, patience=30)
    model.fit(X, y)
    assert set(np.unique(model.predict(X))) <= {0, 1}
