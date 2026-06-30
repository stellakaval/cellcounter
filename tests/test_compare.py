"""Tests for compare.py — marker positivity and colocalization readouts."""

from __future__ import annotations

import numpy as np

from cellcounter import compare


def _labels_from(mask_ch0):
    from skimage.measure import label

    return label(mask_ch0 > 0).astype(np.int32)


def test_edu_percentage(two_channel):
    # ch0 = 3 nuclei; ch1 (EdU) bright over exactly 2 of them -> 2/3 = 66.67%.
    labels = _labels_from(two_channel[0])
    res = compare.colocalize(labels, two_channel[1])
    assert res.n_nuclei == 3
    assert res.n_edu_pos == 2
    assert abs(res.pct_edu_pos - 66.67) < 0.1


def test_marker_intensity_per_nucleus(two_channel):
    labels = _labels_from(two_channel[0])
    df = compare.marker_intensity(labels, two_channel[1])
    assert len(df) == 3
    # Two nuclei fully EdU+ (mean ~1.0), one EdU- (mean ~0.0).
    means = sorted(df["intensity_mean"])
    assert means[0] < 0.5 and means[1] > 0.5 and means[2] > 0.5


def test_positive_mask_with_explicit_threshold():
    vals = np.array([0.0, 0.0, 1.0, 1.0])
    pos = compare.positive_mask(vals, threshold=0.5)
    assert pos.tolist() == [False, False, True, True]


def test_pdgfra_gated_readout(two_channel):
    # Make a PDGFRa channel positive (peri-nuclear) for the two EdU+ nuclei.
    labels = _labels_from(two_channel[0])
    pdgfra = compare._ring_labels(labels, 2.0)
    # Signal only around nuclei 1 and 2 (the EdU+ ones share those label ids by construction).
    edu_labels = sorted(np.unique(labels[two_channel[1] > 0]))
    pdgfra_signal = np.isin(pdgfra, edu_labels).astype(np.float32)
    res = compare.colocalize(labels, two_channel[1], pdgfra_signal, pixel_um=1.0)
    assert res.n_pdgfra_pos is not None and res.n_pdgfra_pos >= 2
    # Both PDGFRa+ nuclei are also EdU+ -> 100%.
    assert res.pct_edu_in_pdgfra is not None
    assert res.pct_edu_in_pdgfra >= 99.0


def test_empty():
    res = compare.colocalize(np.zeros((8, 8), np.int32), np.zeros((8, 8), np.float32))
    assert res.n_nuclei == 0 and res.pct_edu_pos == 0.0
