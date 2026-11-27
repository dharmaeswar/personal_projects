import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsi_agent import data, features  # noqa: E402


def test_feature_vector_length():
    tile = data.Tile(0, 0, True, (128.0, 148.0), 50, 0.05)
    vec = features.extract_features(tile)
    assert len(vec) == features.FEATURE_DIM
    assert all(isinstance(v, float) for v in vec)


def test_feature_vector_deterministic():
    tile = data.Tile(0, 0, True, (128.0, 148.0), 50, 0.05)
    assert features.extract_features(tile) == features.extract_features(tile)


def test_slide_embedding_is_mean_of_tiles():
    slide = data.make_slide("S1", "treated", rows=2, cols=2, seed=1)
    usable = [t for t in slide.tiles if t.tissue]
    emb = features.slide_embedding(usable)
    assert emb is not None and len(emb) == features.FEATURE_DIM
    assert features.slide_embedding([]) is None


def test_tile_score_higher_for_more_nuclei():
    low = data.Tile(0, 0, True, (128.0, 148.0), 10, 0.05)
    high = data.Tile(0, 1, True, (128.0, 148.0), 90, 0.05)
    assert features.tile_score(high) > features.tile_score(low)
