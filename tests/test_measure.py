"""Tests for measure.py — counts, µm² scaling, and non-destructive filtering."""

from __future__ import annotations

import numpy as np

from cellcounter import measure


def test_count_matches_labels(labels_3):
    assert measure.count(labels_3, pixel_um=1.0) == 3


def test_area_um2_scales_with_pixel_size(labels_3):
    df1 = measure.regionprops_df(labels_3, pixel_um=1.0)
    df2 = measure.regionprops_df(labels_3, pixel_um=2.0)
    # Doubling pixel size quadruples µm² area (area_um2 = area_px * pixel_um**2).
    np.testing.assert_allclose(
        df2["area_um2"].to_numpy(), 4.0 * df1["area_um2"].to_numpy()
    )
    np.testing.assert_allclose(df1["area_px"].to_numpy(), df1["area_um2"].to_numpy())


def test_min_area_filter_drops_small_blobs(labels_3):
    # Blob areas (px) ~ 29, 81, 149 for radii 3,5,7. With pixel_um=1, µm²==px.
    areas = sorted(measure.regionprops_df(labels_3, 1.0)["area_um2"])
    # A threshold between the smallest and middle blob keeps 2.
    thresh = (areas[0] + areas[1]) / 2
    assert measure.count(labels_3, 1.0, min_um2=thresh) == 2
    # Above the largest keeps 0; below the smallest keeps all 3.
    assert measure.count(labels_3, 1.0, min_um2=areas[-1] + 1) == 0
    assert measure.count(labels_3, 1.0, min_um2=0) == 3


def test_max_area_filter(labels_3):
    areas = sorted(measure.regionprops_df(labels_3, 1.0)["area_um2"])
    thresh = (areas[1] + areas[2]) / 2  # keep the two smaller
    assert measure.count(labels_3, 1.0, max_um2=thresh) == 2


def test_filtering_is_nondestructive(labels_3):
    before = labels_3.copy()
    measure.measure(labels_3, 1.0, min_um2=1000)  # filters everything out
    np.testing.assert_array_equal(labels_3, before)  # label image untouched


def test_circularity_bounds(labels_3):
    df = measure.regionprops_df(labels_3, 1.0)
    assert (df["circularity"] <= 1.0).all()
    assert (df["circularity"] > 0.5).all()  # disks are reasonably circular


def test_empty_labels():
    empty = np.zeros((16, 16), dtype=np.int32)
    assert measure.count(empty, 1.0) == 0
    assert measure.regionprops_df(empty, 1.0).empty


def test_export_csv(tmp_path, labels_3):
    df = measure.measure(labels_3, 1.0)
    summary = {"count": len(df), "pixel_um": 1.0}
    cells_p, sum_p = measure.export_csv(df, summary, tmp_path / "out.csv")
    assert cells_p.exists() and sum_p.exists()
    import pandas as pd

    assert len(pd.read_csv(cells_p)) == 3
    assert pd.read_csv(sum_p)["count"].iloc[0] == 3
