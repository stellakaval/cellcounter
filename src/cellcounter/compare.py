"""Marker positivity and cross-channel colocalization readouts.

Replaces the lab's manual "repeat per channel + cross-compare in the ROI Manager" step.
Given DAPI nuclei labels and the other channels, decide per nucleus whether it is positive
for a marker, then report the numbers the lab actually uses:

- per-channel nucleus count,
- **% EdU+ nuclei** (proliferating),
- **% EdU+ within PDGFRa+ OPCs** (triple-channel gating).

Positivity = mean marker intensity sampled per nucleus, vs a threshold (Otsu by default).
EdU is nuclear → sample inside the nucleus mask. PDGFRa is a surface/peri-nuclear marker →
sample a dilated ring around the nucleus (``skimage.segmentation.expand_labels``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def _per_label_mean(labels: np.ndarray, intensity: np.ndarray) -> pd.DataFrame:
    """Mean intensity of ``intensity`` within each nonzero label region."""
    from skimage.measure import regionprops_table

    if labels.max() == 0:
        return pd.DataFrame(columns=["label", "intensity_mean"])
    t = regionprops_table(
        labels, intensity_image=intensity, properties=["label", "intensity_mean"]
    )
    return pd.DataFrame({"label": t["label"].astype(int), "intensity_mean": t["intensity_mean"]})


def _ring_labels(labels: np.ndarray, ring_px: float) -> np.ndarray:
    """A peri-nuclear ring per nucleus: dilate labels, then remove the original nuclei."""
    from skimage.segmentation import expand_labels

    if ring_px <= 0:
        return labels
    expanded = expand_labels(labels, distance=ring_px)
    expanded = expanded.copy()
    expanded[labels > 0] = 0  # keep only the shell around each nucleus
    return expanded


def marker_intensity(
    labels: np.ndarray,
    channel: np.ndarray,
    *,
    peri_nuclear_um: float = 0.0,
    pixel_um: float | None = None,
) -> pd.DataFrame:
    """Per-nucleus mean intensity of a marker channel.

    ``peri_nuclear_um`` > 0 samples a ring of that width *around* each nucleus instead of
    inside it (for surface markers like PDGFRa); needs ``pixel_um`` to convert µm → pixels.
    Returns columns ``label``, ``intensity_mean`` (one row per nucleus).
    """
    if peri_nuclear_um and pixel_um:
        ring = _ring_labels(labels, peri_nuclear_um / pixel_um)
        means = _per_label_mean(ring, channel)
        # Nuclei whose ring fell outside the image get no row; fill them with 0.
        all_labels = pd.DataFrame({"label": np.unique(labels[labels > 0]).astype(int)})
        return all_labels.merge(means, on="label", how="left").fillna({"intensity_mean": 0.0})
    return _per_label_mean(labels, channel)


def positive_mask(intensity_mean: np.ndarray, threshold: float | None = None) -> np.ndarray:
    """Boolean positivity per nucleus. Default threshold = Otsu over the per-nucleus means."""
    vals = np.asarray(intensity_mean, dtype=float)
    if vals.size == 0:
        return np.zeros(0, dtype=bool)
    if threshold is None:
        threshold = _otsu(vals)
    return vals > threshold


def _otsu(vals: np.ndarray) -> float:
    from skimage.filters import threshold_otsu

    if np.allclose(vals, vals[0]):  # threshold_otsu needs >1 distinct value
        return float(vals[0])
    return float(threshold_otsu(vals))


@dataclass
class ColocResult:
    n_nuclei: int
    n_edu_pos: int
    pct_edu_pos: float
    n_pdgfra_pos: int | None = None
    pct_edu_in_pdgfra: float | None = None

    def as_dict(self) -> dict:
        return {
            "n_nuclei": self.n_nuclei,
            "n_edu_pos": self.n_edu_pos,
            "pct_edu_pos": self.pct_edu_pos,
            "n_pdgfra_pos": self.n_pdgfra_pos,
            "pct_edu_in_pdgfra": self.pct_edu_in_pdgfra,
        }


def colocalize(
    nuclei_labels: np.ndarray,
    edu_channel: np.ndarray,
    pdgfra_channel: np.ndarray | None = None,
    *,
    pixel_um: float | None = None,
    edu_threshold: float | None = None,
    pdgfra_threshold: float | None = None,
    pdgfra_ring_um: float = 2.0,
) -> ColocResult:
    """Compute the lab's readouts from DAPI nuclei + marker channels.

    %EdU+ = EdU-positive nuclei / all nuclei. If a PDGFRa channel is given, also report
    %EdU+ within PDGFRa+ nuclei (PDGFRa sampled in a peri-nuclear ring).
    """
    n = int((np.unique(nuclei_labels) != 0).sum())
    if n == 0:
        return ColocResult(0, 0, 0.0)

    edu = marker_intensity(nuclei_labels, edu_channel)
    edu_pos = positive_mask(edu["intensity_mean"].to_numpy(), edu_threshold)
    n_edu = int(edu_pos.sum())
    pct_edu = round(100.0 * n_edu / n, 2)

    if pdgfra_channel is None:
        return ColocResult(n, n_edu, pct_edu)

    pdgfra = marker_intensity(
        nuclei_labels, pdgfra_channel, peri_nuclear_um=pdgfra_ring_um, pixel_um=pixel_um
    )
    # Align EdU and PDGFRa positivity by label.
    merged = edu.merge(pdgfra, on="label", suffixes=("_edu", "_pdgfra"))
    edu_pos_m = positive_mask(merged["intensity_mean_edu"].to_numpy(), edu_threshold)
    pdgfra_pos_m = positive_mask(merged["intensity_mean_pdgfra"].to_numpy(), pdgfra_threshold)
    n_pdgfra = int(pdgfra_pos_m.sum())
    pct_edu_in_pdgfra = (
        round(100.0 * int((edu_pos_m & pdgfra_pos_m).sum()) / n_pdgfra, 2)
        if n_pdgfra
        else None
    )
    return ColocResult(n, n_edu, pct_edu, n_pdgfra, pct_edu_in_pdgfra)
