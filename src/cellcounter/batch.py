"""Folder batch processing → one combined CSV. Replaces the lab's Fiji macro.

Applies the same model + pixel size + filters (and optional colocalization) to every image
in a folder and writes a single CSV with one row per image. Pure/headless so it is testable
and can run off the UI thread.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from . import compare, io, measure, segment

IMAGE_EXTS = {".czi", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}


def list_images(folder: str | Path) -> list[Path]:
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in IMAGE_EXTS)


def process_image(
    path: str | Path,
    *,
    model_name: str = segment.STARDIST,
    sensitivity: float = 0.5,
    pixel_um: float | None = None,
    min_um2: float = 30.0,  # ~6 µm nucleus; filters small noise (validated vs ground truth)
    max_um2: float | None = None,
    min_circ: float = 0.0,
    edu_channel: int | None = None,
    pdgfra_channel: int | None = None,
) -> dict:
    """Count one image (and optional colocalization); return a one-row summary dict.

    ``pixel_um`` overrides the file's own pixel size when given; otherwise the metadata value
    is used. ``edu_channel``/``pdgfra_channel`` are channel indices (None to skip).
    """
    path = Path(path)
    img = io.load_image(path)
    px = pixel_um or img.pixel_um
    labels = segment.segment(img.nuclei(), model_name, sensitivity, px)
    n = measure.count(labels, px, min_um2, max_um2, min_circ)

    row = {
        "image": path.name,
        "n_nuclei": n,
        "pixel_um": px,
        "n_channels": img.n_channels,
    }
    if edu_channel is not None and img.n_channels > edu_channel:
        pdgfra = (
            img.channel(pdgfra_channel)
            if pdgfra_channel is not None and img.n_channels > pdgfra_channel
            else None
        )
        res = compare.colocalize(labels, img.channel(edu_channel), pdgfra, pixel_um=px)
        row.update(
            {
                "pct_edu_pos": res.pct_edu_pos,
                "n_edu_pos": res.n_edu_pos,
                "pct_edu_in_pdgfra": res.pct_edu_in_pdgfra,
                "n_pdgfra_pos": res.n_pdgfra_pos,
            }
        )
    return row


def batch_folder(
    folder: str | Path,
    out_csv: str | Path,
    *,
    progress: Callable[[int, int, str], None] | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Process every image in ``folder``, write one combined CSV, and return the table.

    ``progress(done, total, name)`` is called after each image (for a UI progress bar).
    Per-image errors are recorded in an ``error`` column instead of aborting the run.
    """
    images = list_images(folder)
    rows = []
    for i, path in enumerate(images, start=1):
        try:
            rows.append(process_image(path, **kwargs))
        except Exception as e:  # noqa: BLE001 — one bad file shouldn't kill the batch
            rows.append({"image": path.name, "error": str(e)})
        if progress:
            progress(i, len(images), path.name)
    df = pd.DataFrame(rows)
    df.to_csv(out_csv, index=False, float_format="%.6g")
    return df
