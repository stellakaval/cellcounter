"""Per-cell measurements, size/circularity filtering, and counts.

Replaces Fiji's "Analyze Particles": one row per cell with area in µm² and circularity,
filtered **non-destructively** (row selection only — never mutates the label image) so the
widget can recount live as sliders move or after hand edits.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# regionprops properties we request (scikit-image >= 0.26 names).
_BASE_PROPS = ["label", "centroid", "area", "perimeter"]


def regionprops_df(
    labels: np.ndarray, pixel_um: float | None = None
) -> pd.DataFrame:
    """One row per labelled cell with geometry, area in px and (if known) µm², circularity.

    No filtering here — this is the raw table the live filters select rows from.
    """
    from skimage.measure import regionprops_table

    if labels is None or labels.max() == 0:
        cols = [
            "label", "centroid_x", "centroid_y", "area_px", "area_um2",
            "perimeter", "circularity",
        ]
        return pd.DataFrame(columns=cols)

    t = regionprops_table(labels, properties=_BASE_PROPS)
    area = t["area"].astype(float)
    peri = t["perimeter"].astype(float)
    circ = np.where(peri > 0, 4 * np.pi * area / np.square(peri), 0.0)
    circ = np.minimum(circ, 1.0)
    area_um2 = area * (pixel_um**2) if pixel_um else np.full_like(area, np.nan)

    return pd.DataFrame(
        {
            "label": t["label"].astype(int),
            "centroid_x": t["centroid-1"].astype(float),  # column (x)
            "centroid_y": t["centroid-0"].astype(float),  # row (y)
            "area_px": area,
            "area_um2": area_um2,
            "perimeter": peri,
            "circularity": circ,
        }
    )


def contours_df(
    labels: np.ndarray, tolerance: float = 1.0
) -> pd.DataFrame:
    """One row per labelled cell: its outline as a simplified polygon (image px coords).

    Used by the web overlay (colored outlines + numbered labels). Works per-object on the
    region's small bbox crop — ``find_contours`` on the whole image then masking per label
    would be O(image) per cell. The longest contour is kept, offset back to image
    coordinates, and Douglas–Peucker–simplified (``approximate_polygon``) to cut vertices.

    Returns columns ``label`` (int) and ``polygon`` (list of ``[x, y]`` int pairs, where x is
    column and y is row — same convention as ``regionprops_df``'s centroid_x/centroid_y).
    Merge with ``regionprops_df`` on ``label`` so each detection carries geometry + measures.
    """
    from skimage.measure import approximate_polygon, find_contours, regionprops

    if labels is None or labels.max() == 0:
        return pd.DataFrame(columns=["label", "polygon"])

    rows = []
    for region in regionprops(labels):
        min_row, min_col, _, _ = region.bbox
        # Pad the crop by 1px so contours of objects touching the bbox edge close cleanly.
        crop = np.pad(region.image.astype(float), 1, mode="constant")
        contours = find_contours(crop, 0.5)
        if not contours:
            continue
        contour = max(contours, key=len)  # (row, col) coords in padded-crop space
        contour = approximate_polygon(contour, tolerance=tolerance)
        # Undo the 1px pad, offset to full-image coords, emit as [x(col), y(row)].
        poly = [
            [int(round(c - 1 + min_col)), int(round(r - 1 + min_row))]
            for r, c in contour
        ]
        rows.append({"label": int(region.label), "polygon": poly})

    return pd.DataFrame(rows, columns=["label", "polygon"])


def apply_filters(
    df: pd.DataFrame,
    pixel_um: float | None,
    min_um2: float = 0.0,
    max_um2: float | None = None,
    min_circ: float = 0.0,
) -> pd.DataFrame:
    """Return the subset of rows passing the size (µm²) and circularity filters.

    If pixel size is unknown, the µm² filters are ignored (areas are NaN); circularity still
    applies. Filtering selects rows only — the label image is never modified.
    """
    if df.empty:
        return df
    keep = df["circularity"] >= min_circ
    if pixel_um:
        keep &= df["area_um2"] >= min_um2
        if max_um2 is not None and max_um2 > 0:
            keep &= df["area_um2"] <= max_um2
    return df[keep]


def measure(
    labels: np.ndarray,
    pixel_um: float | None,
    min_um2: float = 0.0,
    max_um2: float | None = None,
    min_circ: float = 0.0,
) -> pd.DataFrame:
    """regionprops + filter in one call (one row per surviving cell)."""
    return apply_filters(
        regionprops_df(labels, pixel_um), pixel_um, min_um2, max_um2, min_circ
    )


def count(
    labels: np.ndarray,
    pixel_um: float | None = None,
    min_um2: float = 0.0,
    max_um2: float | None = None,
    min_circ: float = 0.0,
) -> int:
    """Number of cells surviving the filters."""
    return int(len(measure(labels, pixel_um, min_um2, max_um2, min_circ)))


def export_csv(
    cells: pd.DataFrame,
    summary: dict,
    cells_path: str | Path,
    summary_path: str | Path | None = None,
) -> tuple[Path, Path]:
    """Write per-cell rows and a one-row summary (two files). Returns the paths written."""
    cells_path = Path(cells_path)
    cells.to_csv(cells_path, index=False, float_format="%.4g")
    if summary_path is None:
        summary_path = cells_path.with_name(cells_path.stem + "_summary.csv")
    summary_path = Path(summary_path)
    pd.DataFrame([summary]).to_csv(summary_path, index=False, float_format="%.6g")
    return cells_path, summary_path
