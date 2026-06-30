"""Tests for classify.py and dye-based channel detection (io.py)."""

from __future__ import annotations

import numpy as np
from skimage.measure import label

from cellcounter import classify
from cellcounter.io import ImageData


def _synthetic_4channel():
    """4 nuclei: PDGFRa+/EdU-, PDGFRa+/EdU+, ASPA+/EdU-, ASPA+/EdU+ (markers peri-nuclear)."""
    H = W = 64
    yy, xx = np.mgrid[0:H, 0:W]
    centers = [(15, 15), (15, 48), (48, 15), (48, 48)]
    dapi = np.zeros((H, W), np.float32)
    for cy, cx in centers:
        dapi[(yy - cy) ** 2 + (xx - cx) ** 2 <= 7**2] = 1.0  # ~big enough to pass 30 µm²
    labels = label(dapi > 0).astype(np.int32)

    # Marker channels: bright in a disk slightly larger than the nucleus (peri-nuclear ring).
    def ring(idxs):
        ch = np.zeros((H, W), np.float32)
        for i in idxs:
            cy, cx = centers[i]
            ch[(yy - cy) ** 2 + (xx - cx) ** 2 <= 9**2] = 1.0
        return ch

    pdgfra = ring([0, 1])  # nuclei 0,1 are PDGFRa+
    aspa = ring([2, 3])    # nuclei 2,3 are ASPA+
    edu = np.zeros((H, W), np.float32)
    for i in (1, 3):       # nuclei 1,3 are EdU+ (nuclear)
        cy, cx = centers[i]
        edu[(yy - cy) ** 2 + (xx - cx) ** 2 <= 7**2] = 1.0

    arr = np.stack([pdgfra, edu, aspa, dapi])  # DAPI is channel 3 (not 0!)
    img = ImageData(
        array=arr, channel_axis=0,
        channel_names=["PDGFRa", "EdU", "ASPA", "DAPI"], pixel_um=1.0,
        markers={"PDGFRa": 0, "EdU": 1, "ASPA": 2, "DAPI": 3},
    )
    return labels, img


def test_category_counts_recovers_known_classes():
    labels, img = _synthetic_4channel()
    # Explicit thresholds (the percentile defaults assume many cells; here there are 4).
    counts = classify.classify_counts(
        labels, img, min_um2=10, ring_um=2.0,
        thresholds={"PDGFRa": 0.5, "ASPA": 0.5, "EdU": 0.5},
    )
    assert counts["n_cells"] == 4
    assert counts["PDGFRa+/EdU-"] == 1
    assert counts["PDGFRa+/EdU+"] == 1
    assert counts["ASPA+/EdU-"] == 1
    assert counts["ASPA+/EdU+"] == 1
    assert counts["double_positive"] == 0  # OPC and oligo markers are mutually exclusive here


def test_nuclei_uses_dapi_channel_not_index_zero():
    _, img = _synthetic_4channel()
    # DAPI is channel 3; nuclei() must return it (channel 0 here is PDGFRa).
    assert img.marker_index("DAPI") == 3
    np.testing.assert_array_equal(img.nuclei(), img.channel(3))


def test_dye_detection_when_dapi_is_last():
    # Fake CZI metadata: 4 channels, DAPI last; filename names the fluorophores.
    from cellcounter import io

    meta = (
        '<Channel Id="Channel:0"><Fluor>Alexa Fluor 647</Fluor></Channel>'
        '<Channel Id="Channel:1"><Fluor>Alexa Fluor 594</Fluor></Channel>'
        '<Channel Id="Channel:2"><Fluor>Alexa Fluor 488</Fluor></Channel>'
        '<Channel Id="Channel:3"><Fluor>DAPI</Fluor></Channel>'
    )
    markers = io._czi_markers(meta, "M1 #1 PDGFRa647 ASPA488 EdU594 DAPI405-7514.czi", 4)
    assert markers == {"PDGFRa": 0, "EdU": 1, "ASPA": 2, "DAPI": 3}
