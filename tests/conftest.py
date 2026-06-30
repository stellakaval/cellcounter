"""Shared synthetic fixtures — no real or licensed data needed; fast and deterministic."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def labels_3():
    """A 64x64 label image with exactly 3 disjoint blobs of known, different sizes."""
    lab = np.zeros((64, 64), dtype=np.int32)
    yy, xx = np.mgrid[0:64, 0:64]
    # radii 3, 5, 7 -> areas ~ pi r^2
    for i, (cy, cx, r) in enumerate([(12, 12, 3), (12, 45, 5), (45, 25, 7)], start=1):
        lab[(yy - cy) ** 2 + (xx - cx) ** 2 <= r**2] = i
    return lab


@pytest.fixture
def two_channel():
    """(2, 64, 64) image: ch0 = 3 nuclei, ch1 = bright signal over 2 of them (EdU+)."""
    yy, xx = np.mgrid[0:64, 0:64]
    ch0 = np.zeros((64, 64), np.float32)
    ch1 = np.zeros((64, 64), np.float32)
    centers = [(12, 12, 5), (12, 45, 5), (45, 25, 5)]
    for cy, cx, r in centers:
        ch0[(yy - cy) ** 2 + (xx - cx) ** 2 <= r**2] = 1.0
    # EdU-positive in the first two nuclei only.
    for cy, cx, r in centers[:2]:
        ch1[(yy - cy) ** 2 + (xx - cx) ** 2 <= r**2] = 1.0
    return np.stack([ch0, ch1])
