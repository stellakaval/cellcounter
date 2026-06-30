"""Render an image channel to an 8-bit PNG for the browser.

Microscopy DAPI is dim and ``io.load_image`` returns float32, so we contrast-stretch with
the same robust 1–99.5 percentile limits the napari app uses (``io._percentile_limits``)
before saving. PNGs are cached on disk and re-served.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cellcounter.io import _percentile_limits


def _to_uint8(plane: np.ndarray) -> np.ndarray:
    lo, hi = _percentile_limits(plane)
    scaled = (plane.astype(np.float32) - lo) / (hi - lo)
    return (np.clip(scaled, 0.0, 1.0) * 255).astype(np.uint8)


def render_png(plane: np.ndarray, out_path: str | Path) -> Path:
    """Contrast-stretch a 2D plane and write it as PNG. Returns the path."""
    from PIL import Image as PILImage

    out_path = Path(out_path)
    PILImage.fromarray(_to_uint8(plane), mode="L").save(out_path)
    return out_path


def render_thumbnail(plane: np.ndarray, out_path: str | Path, size: int = 256) -> Path:
    from PIL import Image as PILImage

    out_path = Path(out_path)
    im = PILImage.fromarray(_to_uint8(plane), mode="L")
    im.thumbnail((size, size))
    im.save(out_path)
    return out_path
