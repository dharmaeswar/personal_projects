"""Preprocessing for gigapixel whole-slide images (simulated tiles).

Mirrors the real pipeline: tile extraction, tissue detection, stain
normalisation to a reference, and QC flags for tiles that must not
reach the model (empty, out of focus, or stain outliers).
"""

REFERENCE_STAIN = (128.0, 148.0)  # reference (H, E) means
BLUR_LIMIT = 0.35  # tiles blurrier than this fail QC
MIN_NUCLEI_FOR_TISSUE = 3


def tissue_mask(slide):
    """Return the tiles that contain tissue (the analysis region)."""
    return [t for t in slide.tiles
            if t.tissue and t.nuclei >= MIN_NUCLEI_FOR_TISSUE]


def stain_factors(tile, reference=REFERENCE_STAIN):
    """Per-channel scale factors that map a tile onto the reference stain.

    A factor of 1.0 means the tile already matches the reference.
    """
    h, e = tile.stain
    return (reference[0] / h if h > 0 else 1.0,
            reference[1] / e if e > 0 else 1.0)


def normalise_tile(tile, reference=REFERENCE_STAIN):
    """Return a stain-normalised copy of a tile (stain vector scaled)."""
    from .data import Tile
    fh, fe = stain_factors(tile, reference)
    stain = (round(tile.stain[0] * fh, 1), round(tile.stain[1] * fe, 1))
    return Tile(tile.row, tile.col, tile.tissue, stain, tile.nuclei,
                tile.blur)


def qc_tile(tile):
    """QC verdict for one tile. Returns (passed, reasons list)."""
    reasons = []
    if not tile.tissue:
        reasons.append("no-tissue")
    if tile.blur > BLUR_LIMIT:
        reasons.append("out-of-focus")
    if tile.tissue and tile.nuclei < MIN_NUCLEI_FOR_TISSUE:
        reasons.append("too-few-nuclei")
    fh, fe = stain_factors(tile)
    if not (0.7 <= fh <= 1.4) or not (0.7 <= fe <= 1.4):
        reasons.append("stain-outlier")
    return (len(reasons) == 0, reasons)


def preprocess_slide(slide):
    """Full preprocessing: tissue tiles, normalised tiles, QC summary.

    Returns a dict with the usable tiles (tissue + QC pass), the
    normalised tile list, and counts for the QC report.
    """
    tissue = tissue_mask(slide)
    usable, rejected = [], []
    normalised = []
    for tile in tissue:
        passed, reasons = qc_tile(tile)
        if passed:
            usable.append(tile)
            normalised.append(normalise_tile(tile))
        else:
            rejected.append((tile, reasons))
    return {
        "slide_id": slide.slide_id,
        "total_tiles": slide.tile_count,
        "tissue_tiles": len(tissue),
        "usable_tiles": len(usable),
        "rejected_tiles": len(rejected),
        "rejected": [(t.row, t.col, r) for t, r in rejected],
        "usable": usable,
        "normalised": normalised,
    }
