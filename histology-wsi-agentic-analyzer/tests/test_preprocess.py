import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsi_agent import data, preprocess  # noqa: E402


def test_make_slide_tile_count():
    slide = data.make_slide("S1", "treated", rows=4, cols=5, seed=1)
    assert slide.tile_count == 20
    assert len(slide.tissue_tiles()) <= 20


def test_make_slide_seeded_reproducible():
    a = data.make_slide("S1", "treated", seed=3)
    b = data.make_slide("S1", "treated", seed=3)
    assert [t.nuclei for t in a.tiles] == [t.nuclei for t in b.tiles]
    c = data.make_slide("S1", "treated", seed=4)
    assert [t.nuclei for t in a.tiles] != [t.nuclei for t in c.tiles]


def test_preprocess_counts_add_up():
    slide = data.make_slide("S1", "treated", seed=5)
    prep = preprocess.preprocess_slide(slide)
    assert prep["usable_tiles"] + prep["rejected_tiles"] == prep["tissue_tiles"]
    assert prep["tissue_tiles"] <= prep["total_tiles"]


def test_qc_rejects_blurry_tile():
    tile = data.Tile(0, 0, True, (128.0, 148.0), 50, 0.9)
    passed, reasons = preprocess.qc_tile(tile)
    assert not passed
    assert "out-of-focus" in reasons


def test_stain_normalisation_maps_to_reference():
    tile = data.Tile(0, 0, True, (64.0, 74.0), 50, 0.05)
    normed = preprocess.normalise_tile(tile)
    assert normed.stain == (128.0, 148.0)
