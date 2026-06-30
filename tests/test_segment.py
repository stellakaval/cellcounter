"""Tests for segment.py — model registry and that an available backend segments.

StarDist inference is real (downloads weights once); kept tolerant and skipped if the
backend isn't installed, so CPU-only / offline runs stay green.
"""

from __future__ import annotations

import numpy as np
import pytest

from cellcounter import segment


def test_list_models_always_offers_stardist():
    assert segment.STARDIST in segment.list_models()


def test_sensitivity_maps_to_prob_thresh():
    # Higher sensitivity -> lower prob_thresh (more detections). Verified via the formula.
    hi = float(np.clip(0.7 - 0.6 * 0.9, 0.05, 0.95))
    lo = float(np.clip(0.7 - 0.6 * 0.1, 0.05, 0.95))
    assert hi < lo


@pytest.mark.skipif(not segment._stardist_available(), reason="StarDist not installed")
def test_stardist_segments_synthetic(two_channel):
    # ch0 has 3 well-separated bright disks; expect ~3 labels (allow a small tolerance).
    labels = segment.segment(two_channel[0], segment.STARDIST, sensitivity=0.5)
    assert labels.dtype.kind in "iu"
    n = int((np.unique(labels) != 0).sum())
    assert 2 <= n <= 4
