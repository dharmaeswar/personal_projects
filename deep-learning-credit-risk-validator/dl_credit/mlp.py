"""A small feed-forward neural network (MLP) written from scratch in NumPy.

Two hidden layers with ReLU, a sigmoid output, mini-batch gradient descent
with momentum and L2 regularisation, and early stopping on validation loss.
No deep-learning framework is used: every forward pass, gradient, and
weight update is explicit, so the training code itself is auditable — the
way a validator wants to see a model built before it is approved.
"""
import numpy as np


def _relu(z):
    return np.maximum(0.0, z)


def _relu_grad(z):
    return (z > 0).astype(float)


def _sigmoid(z):
    z = np.clip(z, -30.0, 30.0)
    return 1.0 / (1.0 + np.exp(-z))


class MLPClassifier:
    """Binary MLP classifier with two hidden layers."""

    def __init__(self, hidden=(32, 16), lr=0.05, momentum=0.9, l2=1e-4,
                 epochs=300, batch_size=256, patience=25, seed=7):
        self.hidden = tuple(hidden)
        self.lr = lr
        self.momentum = momentum
        self.l2 = l2
        self.epochs = epochs
        self.batch_size = batch_size
        self.patience = patience
        self.seed = seed
        self.weights_ = None
        self.biases_ = None
        self.n_epochs_run_ = 0
        self.train_loss_ = []
        self.val_loss_ = []

    def _init(self, n_in, rng):
        sizes = [n_in] + list(self.hidden) + [1]
        self.weights_ = []
        self.biases_ = []
        for a, b in zip(sizes[:-1], sizes[1:]):
            # He initialisation for ReLU layers, small init for the output.
            scale = np.sqrt(2.0 / a) if b != 1 else np.sqrt(1.0 / a)
            self.weights_.append(rng.normal(0.0, scale, (a, b)))
            self.biases_.append(np.zeros(b))

    def _forward(self, X):
        activations = [X]
        pre = []
        a = X
        for i, (W, b) in enumerate(zip(self.weights_, self.biases_)):
            z = a @ W + b
            pre.append(z)
            a = _relu(z) if i < len(self.weights_) - 1 else _sigmoid(z)
            activations.append(a)
        return activations, pre

    @staticmethod
    def _loss(y, p, weights, l2):
        eps = 1e-12
        p = np.clip(p, eps, 1 - eps)
        n = len(y)
        ce = -np.mean(y * np.log(p) + (1 - y) * np.log(1 - p))
        reg = 0.5 * l2 * sum(np.sum(W * W) for W in weights)
        return ce + reg

    def fit(self, X, y, X_val=None, y_val=None):
        rng = np.random.default_rng(self.seed)
        n, d = X.shape
        y = y.astype(float).reshape(-1, 1)
        self._init(d, rng)
        vel_w = [np.zeros_like(W) for W in self.weights_]
        vel_b = [np.zeros_like(b) for b in self.biases_]
        best_val = np.inf
        best_w = best_b = None
        bad = 0
        has_val = X_val is not None and y_val is not None
        if has_val:
            y_val = y_val.astype(float).reshape(-1, 1)

        for epoch in range(self.epochs):
            perm = rng.permutation(n)
            for start in range(0, n, self.batch_size):
                idx = perm[start:start + self.batch_size]
                xb, yb = X[idx], y[idx]
                acts, pre = self._forward(xb)
                m = len(idx)
                delta = (acts[-1] - yb) / m
                grads_w = [None] * len(self.weights_)
                grads_b = [None] * len(self.biases_)
                for i in reversed(range(len(self.weights_))):
                    grads_w[i] = acts[i].T @ delta + self.l2 * self.weights_[i]
                    grads_b[i] = delta.sum(axis=0)
                    if i > 0:
                        delta = (delta @ self.weights_[i].T) * _relu_grad(pre[i - 1])
                for i in range(len(self.weights_)):
                    vel_w[i] = self.momentum * vel_w[i] - self.lr * grads_w[i]
                    vel_b[i] = self.momentum * vel_b[i] - self.lr * grads_b[i]
                    self.weights_[i] += vel_w[i]
                    self.biases_[i] += vel_b[i]
            train_p = self._forward(X)[0][-1]
            self.train_loss_.append(self._loss(y, train_p, self.weights_, self.l2))
            if has_val:
                val_p = self._forward(X_val)[0][-1]
                vl = self._loss(y_val, val_p, self.weights_, self.l2)
                self.val_loss_.append(vl)
                if vl < best_val - 1e-4:
                    best_val = vl
                    best_w = [W.copy() for W in self.weights_]
                    best_b = [b.copy() for b in self.biases_]
                    bad = 0
                else:
                    bad += 1
                    if bad >= self.patience:
                        self.n_epochs_run_ = epoch + 1
                        break
            self.n_epochs_run_ = epoch + 1
        if has_val and best_w is not None:
            self.weights_, self.biases_ = best_w, best_b
        return self

    def predict_proba(self, X):
        return self._forward(np.asarray(X, dtype=float))[0][-1].reshape(-1)

    def predict(self, X, threshold=0.5):
        return (self.predict_proba(X) >= threshold).astype(int)
