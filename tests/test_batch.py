"""Tests for batch.py and session.py — folder→CSV shape and save/load round-trip.

batch_folder calls real segmentation per image; kept to 2 tiny synthetic images and skipped
if StarDist isn't installed.
"""

from __future__ import annotations

import numpy as np
import pytest
import tifffile

from cellcounter import batch, segment, session


def _write_synthetic(path, seed):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:96, 0:96]
    img = np.zeros((96, 96), np.float32)
    for _ in range(5):
        cy, cx = rng.integers(12, 84, size=2)
        img[(yy - cy) ** 2 + (xx - cx) ** 2 <= 6**2] = 1.0
    tifffile.imwrite(path, (img * 255).astype(np.uint8))


def test_list_images(tmp_path):
    _write_synthetic(tmp_path / "a.tif", 0)
    (tmp_path / "notes.txt").write_text("ignore me")
    assert [p.name for p in batch.list_images(tmp_path)] == ["a.tif"]


@pytest.mark.skipif(not segment._stardist_available(), reason="StarDist not installed")
def test_batch_folder_one_row_per_image(tmp_path):
    for i in range(2):
        _write_synthetic(tmp_path / f"img_{i}.tif", i)
    out = tmp_path / "combined.csv"
    df = batch.batch_folder(tmp_path, out, pixel_um=0.5, sensitivity=0.5)
    assert out.exists()
    assert len(df) == 2
    assert set(["image", "n_nuclei", "pixel_um"]).issubset(df.columns)
    assert (df["n_nuclei"] >= 0).all()


def test_session_roundtrip(tmp_path):
    labels = np.zeros((32, 32), np.int32)
    labels[2:8, 2:8] = 1
    labels[20:26, 20:26] = 2
    params = {"model": "StarDist fluo", "pixel_um": 0.62, "min_um2": 10.0}
    session.save_session(tmp_path / "sess", labels, params)
    labels2, params2 = session.load_session(tmp_path / "sess")
    np.testing.assert_array_equal(labels, labels2)
    assert params2 == params
