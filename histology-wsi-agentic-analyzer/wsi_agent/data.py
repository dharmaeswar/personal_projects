"""Synthetic whole-slide image (WSI) data for the demo pipeline.

A gigapixel slide cannot be shipped in a portfolio repo, so this module
simulates one: a slide is a grid of tiles, each tile carrying a small
synthetic stain-colour vector, a tissue flag, and a seeded cell count.
All values are synthetic and seeded; no real histology, patient, or
vendor data is used.
"""

import random

TILE_SIZE_PX = 512


class Tile:
    """One tile of a simulated whole-slide image."""

    def __init__(self, row, col, tissue, stain, nuclei, blur):
        self.row = row
        self.col = col
        self.tissue = tissue  # True when the tile contains tissue
        self.stain = stain  # (hematoxylin, eosin) mean intensities 0-255
        self.nuclei = nuclei  # seeded nuclei count proxy
        self.blur = blur  # 0.0 sharp .. 1.0 badly out of focus

    def __repr__(self):
        return (
            f"Tile(r={self.row}, c={self.col}, tissue={self.tissue}, "
            f"nuclei={self.nuclei}, blur={self.blur:.2f})"
        )


class Slide:
    """A simulated whole-slide image: a grid of tiles plus metadata."""

    def __init__(self, slide_id, rows, cols, tiles, label):
        self.slide_id = slide_id
        self.rows = rows
        self.cols = cols
        self.tiles = tiles  # list[Tile], row-major
        self.label = label  # study arm label, e.g. "treated" / "control"

    @property
    def tile_count(self):
        return len(self.tiles)

    def tissue_tiles(self):
        return [t for t in self.tiles if t.tissue]


def make_slide(slide_id, label, rows=16, cols=16, seed=42,
               tissue_rate=0.62, mean_nuclei=48.0):
    """Build one seeded synthetic slide.

    Nuclei counts are drawn around ``mean_nuclei`` (higher for the
    "treated" arm in the demo so the statistics module has a real
    difference to find). Blur is mostly low with a few bad tiles.
    """
    rng = random.Random(seed)
    # Slide-level random effect: real slides vary more than tiles do,
    # so the arm comparison has realistic (not inflated) power.
    slide_offset = rng.gauss(0.0, 5.0)
    tiles = []
    for r in range(rows):
        for c in range(cols):
            tissue = rng.random() < tissue_rate
            stain = (
                round(rng.uniform(90, 170), 1),
                round(rng.uniform(110, 190), 1),
            )
            nuclei = 0
            if tissue:
                nuclei = max(0, int(rng.gauss(mean_nuclei + slide_offset,
                                              12.0)))
            blur = round(rng.betavariate(1.5, 9.0), 3)
            tiles.append(Tile(r, c, tissue, stain, nuclei, blur))
    return Slide(slide_id, rows, cols, tiles, label)


def make_study(n_per_arm=6, seed=7):
    """Build a small two-arm study: treated vs control slides."""
    slides = []
    for i in range(n_per_arm):
        slides.append(make_slide(
            f"TRT-{i + 1:02d}", "treated", seed=seed + i,
            mean_nuclei=58.0))
    for i in range(n_per_arm):
        slides.append(make_slide(
            f"CTL-{i + 1:02d}", "control", seed=seed + 100 + i,
            mean_nuclei=44.0))
    return slides
