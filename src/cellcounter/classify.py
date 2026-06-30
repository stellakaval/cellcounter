"""Per-cell marker classification (OPC vs oligodendrocyte, ± proliferation).

For datasets that stain PDGFRa (OPC), ASPA (mature oligodendrocyte), EdU (proliferation), and
DAPI (nuclei): segment the DAPI nuclei, then classify each nucleus by marker positivity and
report the four categories the lab uses per region:

    PDGFRa+/EdU+ , PDGFRa+/EdU- , ASPA+/EdU+ , ASPA+/EdU-

Positivity is per-nucleus mean marker intensity vs a threshold (Otsu per image by default,
overridable for tuning). EdU is nuclear (sampled inside the nucleus mask); PDGFRa and ASPA are
membrane/cytoplasmic (sampled in a peri-nuclear ring via ``compare`` helpers). Small debris is
removed first with the same minimum-size filter used for counting.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import compare, measure
from .io import ImageData

CATEGORIES = ["PDGFRa+/EdU+", "PDGFRa+/EdU-", "ASPA+/EdU+", "ASPA+/EdU-"]


def classify_cells(
    nuclei_labels: np.ndarray,
    image: ImageData,
    *,
    min_um2: float = 30.0,
    ring_um: float = 2.0,
    thresholds: dict[str, float] | None = None,
) -> pd.DataFrame:
    """One row per surviving nucleus with per-marker mean intensity + positivity flags.

    ``thresholds`` maps a marker name → fixed positivity threshold; markers absent from it use
    Otsu over that image's per-nucleus means. Markers missing from the image are all-negative.
    """
    pixel_um = image.pixel_um
    thresholds = thresholds or {}

    geo = measure.measure(nuclei_labels, pixel_um, min_um2=min_um2)  # debris removed
    cols = ["label", "area_um2", "edu_mean", "pdgfra_mean", "aspa_mean",
            "edu_pos", "pdgfra_pos", "aspa_pos"]
    if geo.empty:
        return pd.DataFrame(columns=cols)

    out = geo[["label", "area_um2"]].reset_index(drop=True)
    keep = out["label"].astype(int)

    def add_marker(marker: str, peri_nuclear: bool) -> None:
        low = marker.lower()
        idx = image.marker_index(marker)
        if idx is None:
            out[f"{low}_mean"] = np.nan
            out[f"{low}_pos"] = False
            return
        mi = compare.marker_intensity(
            nuclei_labels,
            image.channel(idx),
            peri_nuclear_um=ring_um if peri_nuclear else 0.0,
            pixel_um=pixel_um,
        )
        means = (
            out[["label"]]
            .merge(mi, on="label", how="left")["intensity_mean"]
            .fillna(0.0)
            .to_numpy()
        )
        out[f"{low}_mean"] = means
        out[f"{low}_pos"] = compare.positive_mask(means, thresholds.get(marker))

    add_marker("EdU", peri_nuclear=False)      # nuclear stain
    add_marker("PDGFRa", peri_nuclear=True)    # surface/cytoplasmic
    add_marker("ASPA", peri_nuclear=True)      # cytoplasmic
    return out


def category_counts(df: pd.DataFrame) -> dict:
    """Counts for the four lab categories (+ QA: double-positive and total classified)."""
    if df.empty:
        return {c: 0 for c in CATEGORIES} | {"double_positive": 0, "n_cells": 0}
    p = df["pdgfra_pos"].to_numpy()
    a = df["aspa_pos"].to_numpy()
    e = df["edu_pos"].to_numpy()
    return {
        "PDGFRa+/EdU+": int((p & e).sum()),
        "PDGFRa+/EdU-": int((p & ~e).sum()),
        "ASPA+/EdU+": int((a & e).sum()),
        "ASPA+/EdU-": int((a & ~e).sum()),
        "double_positive": int((p & a).sum()),  # OPC + mature-oligo markers: should be rare
        "n_cells": int(len(df)),
    }


def classify_counts(
    nuclei_labels: np.ndarray, image: ImageData, **kw
) -> dict:
    """Convenience: classify then return the category counts in one call."""
    return category_counts(classify_cells(nuclei_labels, image, **kw))
