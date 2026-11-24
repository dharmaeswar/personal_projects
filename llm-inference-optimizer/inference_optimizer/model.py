"""Model shapes: parameter counts, memory, FLOPs, KV cache.

A transformer model is described by its shape (layers, hidden size,
attention heads, vocabulary, dtype). From the shape alone we can compute
the quantities an inference engineer needs before serving: how many
parameters, how much memory the weights take, how much compute one
generated token costs, and how big the KV cache grows per token.
"""

from dataclasses import dataclass

GIB = 1024 ** 3


@dataclass(frozen=True)
class ModelConfig:
    """Shape of one decoder-only transformer model."""

    name: str
    layers: int
    hidden: int
    heads: int
    vocab: int
    dtype_bytes: int = 2  # fp16 / bf16 default
    intermediate: int = 0  # MLP intermediate size; 0 means 4 * hidden

    def __post_init__(self):
        if self.layers <= 0 or self.hidden <= 0 or self.heads <= 0 or self.vocab <= 0:
            raise ValueError("layers, hidden, heads and vocab must be positive")
        if self.hidden % self.heads != 0:
            raise ValueError("hidden must divide evenly across attention heads")
        if self.dtype_bytes not in (1, 2, 4):
            raise ValueError("dtype_bytes must be 1, 2 or 4")

    @property
    def head_dim(self) -> int:
        return self.hidden // self.heads

    @property
    def intermediate_size(self) -> int:
        return self.intermediate or 4 * self.hidden

    def param_count(self) -> int:
        """Approximate parameter count.

        Per layer: attention Q/K/V/O projections (4 * hidden^2) plus the
        MLP gate/up/down projections (3 * hidden * intermediate). Plus the
        token embedding (vocab * hidden) and a final norm (hidden).
        """
        per_layer = 4 * self.hidden * self.hidden
        per_layer += 3 * self.hidden * self.intermediate_size
        return self.vocab * self.hidden + self.layers * per_layer + self.hidden

    def weight_bytes(self, dtype_bytes=None) -> int:
        db = dtype_bytes if dtype_bytes is not None else self.dtype_bytes
        return self.param_count() * db

    def weight_gb(self, dtype_bytes=None) -> float:
        return self.weight_bytes(dtype_bytes) / GIB

    def flops_per_token(self) -> int:
        """Multiply-add FLOPs for one forward pass of one token (~2 * params)."""
        return 2 * self.param_count()

    def kv_bytes_per_token(self, dtype_bytes=None) -> int:
        """KV-cache bytes for one token: K and V, every layer, every head."""
        db = dtype_bytes if dtype_bytes is not None else self.dtype_bytes
        return 2 * self.layers * self.heads * self.head_dim * db

    def kv_gb(self, batch: int, seq_len: int, dtype_bytes=None) -> float:
        if batch <= 0 or seq_len <= 0:
            raise ValueError("batch and seq_len must be positive")
        return batch * seq_len * self.kv_bytes_per_token(dtype_bytes) / GIB


# Illustrative model shapes, named after the open model families an
# enablement team works with. Shapes are public knowledge; the numbers
# are rounded presets for the optimizer, not measured weights.
PRESETS = {
    "tiny-0.5b": ModelConfig("tiny-0.5b", layers=24, hidden=1024, heads=16, vocab=32000),
    "small-2b": ModelConfig("small-2b", layers=28, hidden=2048, heads=16, vocab=128256),
    "glm-4b": ModelConfig("glm-4b", layers=36, hidden=2560, heads=32, vocab=151936),
    "kimi-8b": ModelConfig("kimi-8b", layers=36, hidden=4096, heads=32, vocab=163840),
}
