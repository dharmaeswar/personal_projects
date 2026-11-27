"""Feature extraction for WSI tiles — stand-in for a vision foundation model.

A real deployment would call a vision foundation model here
(UNI, CONCH, or similar) for tile embeddings and fine-tune a head
downstream. This module keeps the exact same interface —
``extract_features(tile)`` returns a fixed-length feature vector —
but computes deterministic features from the synthetic tile data, so
the pipeline runs and is testable offline with no model weights.
"""

import math

FEATURE_DIM = 6


def extract_features(tile):
    """Deterministic 6-feature vector for one tile.

    Features: stain means (H, E), nuclei density proxy, blur,
    local texture proxy (nuclei spread), and a stain-ratio feature.
    All values are plain floats in documented ranges.
    """
    h, e = tile.stain
    density = tile.nuclei / 100.0
    texture = math.sqrt(tile.nuclei) / 10.0 if tile.nuclei else 0.0
    ratio = h / e if e else 0.0
    return [round(h / 255.0, 4), round(e / 255.0, 4),
            round(density, 4), round(tile.blur, 4),
            round(texture, 4), round(ratio, 4)]


def slide_embedding(tiles):
    """Slide-level embedding: mean of tile feature vectors.

    Returns a FEATURE_DIM list, or None when there are no tiles.
    """
    if not tiles:
        return None
    vectors = [extract_features(t) for t in tiles]
    return [round(sum(v[i] for v in vectors) / len(vectors), 4)
            for i in range(FEATURE_DIM)]


def tile_score(tile, weights=None):
    """A single slide-level score per tile (e.g. tumour-burden proxy).

    Default weights emphasise nuclei density and stain ratio; callers
    may pass their own weight vector of length FEATURE_DIM.
    """
    weights = weights or [0.1, 0.1, 0.6, -0.2, 0.2, 0.2]
    feats = extract_features(tile)
    return round(sum(w * f for w, f in zip(weights, feats)), 4)
