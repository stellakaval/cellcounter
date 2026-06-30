"""Tests for io.py — napari reader contract, channel detection, pixel size."""

from __future__ import annotations

import numpy as np
import tifffile

from cellcounter import io


def test_reader_only_handles_czi():
    assert io.napari_get_reader("foo.czi") is not None
    assert io.napari_get_reader(["foo.czi"]) is not None
    assert io.napari_get_reader("foo.png") is None
    assert io.napari_get_reader("foo.tif") is None


def test_load_single_channel_tiff(tmp_path):
    arr = (np.random.default_rng(0).random((32, 32)) * 255).astype(np.uint8)
    p = tmp_path / "single.tif"
    tifffile.imwrite(p, arr)
    img = io.load_image(p)
    assert img.array.shape == (32, 32)
    assert img.channel_axis is None
    assert img.n_channels == 1
    np.testing.assert_array_equal(img.nuclei(), img.array)


def test_load_multichannel_tiff_is_channels_first(tmp_path):
    arr = (np.random.default_rng(1).random((2, 48, 48)) * 255).astype(np.uint8)
    p = tmp_path / "two.tif"
    tifffile.imwrite(p, arr, imagej=True, metadata={"axes": "CYX"})
    img = io.load_image(p)
    assert img.channel_axis == 0
    assert img.n_channels == 2
    assert img.channel(0).shape == (48, 48)
    # Channel 0 is treated as nuclei (DAPI).
    np.testing.assert_array_equal(img.nuclei(), img.channel(0))


def test_percentile_limits_handles_flat_image():
    lo, hi = io._percentile_limits(np.zeros((8, 8), np.float32))
    assert hi > lo  # guarded against degenerate range


def test_channel_names_from_filename():
    from pathlib import Path

    # Stains are parsed from the filename in channel order; ch0 is always DAPI.
    assert io._channel_names(Path("E3_LDHi_1_1_DAPI__Edu594.czi"), "", 2) == ["DAPI", "EdU"]
    assert io._channel_names(
        Path("APOE_DAPI_488PDGFRa_Edu594.czi"), "", 3
    ) == ["DAPI", "PDGFRa", "EdU"]
    # Falls back to DAPI/Ch1.. when the filename doesn't name the stains.
    assert io._channel_names(Path("mystery.czi"), "", 2) == ["DAPI", "Ch1"]
