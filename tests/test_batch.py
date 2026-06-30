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


def test_batch_default_min_size_is_30um2():
    # The opinionated noise-filter default lives at the application layer (validated value).
    import inspect

    assert inspect.signature(batch.process_image).parameters["min_um2"].default == 30.0


def test_min_size_filters_small_objects():
    # A 30 µm² floor (at 1 µm/px) keeps a big blob and drops a tiny speck.
    from skimage.measure import label

    from cellcounter import measure

    mask = np.zeros((64, 64), np.int32)
    yy, xx = np.mgrid[0:64, 0:64]
    mask[(yy - 20) ** 2 + (xx - 20) ** 2 <= 6**2] = 1  # ~113 µm²  (kept)
    mask[(yy - 50) ** 2 + (xx - 50) ** 2 <= 1**2] = 1  # tiny speck (dropped)
    labels = label(mask)
    assert measure.count(labels, pixel_um=1.0, min_um2=0) == 2
    assert measure.count(labels, pixel_um=1.0, min_um2=30) == 1


def test_session_roundtrip(tmp_path):
    labels = np.zeros((32, 32), np.int32)
    labels[2:8, 2:8] = 1
    labels[20:26, 20:26] = 2
    params = {"model": "StarDist fluo", "pixel_um": 0.62, "min_um2": 10.0}
    session.save_session(tmp_path / "sess", labels, params)
    labels2, params2 = session.load_session(tmp_path / "sess")
    np.testing.assert_array_equal(labels, labels2)
    assert params2 == params
