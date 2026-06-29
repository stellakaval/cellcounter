"""Generate small synthetic microscopy TIFFs for tests and as a pre-real-image fallback.

Each "nucleus" is a filled circle of varied radius placed without overlap on a dark
background, with Gaussian noise and a few tiny specks (to exercise the size filter).
We write a single-channel and a two-channel example (the 2nd channel partly overlapping
the 1st, for later colocalization tests). A known pixel size is embedded in ImageJ TIFF
metadata, and the ground-truth count is printed.

Run:
    python sample_data/make_synthetic.py
This writes TIFFs into the same folder and prints ground-truth counts.

Not product code — this is test/fallback data generation. Deterministic (fixed seed)
so tests have a stable expected count.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import tifffile

# Fixed pixel size so downstream µm² math has a known scale.
PIXEL_UM = 0.5  # microns per pixel


def _place_circles(
    shape: tuple[int, int],
    rng: np.random.Generator,
    n_nuclei: int,
    radius_range: tuple[int, int],
    centers: list[tuple[int, int]] | None = None,
) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Draw non-overlapping filled circles; return (image float32 0..1, list of centers).

    If ``centers`` is given, reuse those positions (used so channel 2 can partly
    overlap channel 1) rather than sampling fresh ones.
    """
    h, w = shape
    img = np.zeros(shape, dtype=np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    placed: list[tuple[int, int]] = []
    radii: list[int] = []

    def overlaps(cy: int, cx: int, r: int) -> bool:
        for (py, px), pr in zip(placed, radii):
            if (cy - py) ** 2 + (cx - px) ** 2 < (r + pr + 3) ** 2:
                return True
        return False

    if centers is None:
        attempts = 0
        while len(placed) < n_nuclei and attempts < n_nuclei * 200:
            attempts += 1
            r = int(rng.integers(radius_range[0], radius_range[1] + 1))
            cy = int(rng.integers(r + 1, h - r - 1))
            cx = int(rng.integers(r + 1, w - r - 1))
            if overlaps(cy, cx, r):
                continue
            placed.append((cy, cx))
            radii.append(r)
    else:
        for (cy, cx) in centers:
            r = int(rng.integers(radius_range[0], radius_range[1] + 1))
            placed.append((cy, cx))
            radii.append(r)

    for (cy, cx), r in zip(placed, radii):
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= r**2
        # Slightly soft, bright blob.
        img[mask] = 0.9
    return img, placed


def _add_noise_and_specks(
    img: np.ndarray, rng: np.random.Generator, n_specks: int = 8
) -> np.ndarray:
    """Add Gaussian noise and a few sub-resolution specks (filter bait)."""
    h, w = img.shape
    out = img.copy()
    for _ in range(n_specks):
        cy = int(rng.integers(2, h - 2))
        cx = int(rng.integers(2, w - 2))
        out[cy, cx] = 0.7  # 1-pixel speck
    out = out + rng.normal(0.0, 0.03, size=img.shape).astype(np.float32)
    return np.clip(out, 0.0, 1.0)


def _to_uint8(img: np.ndarray) -> np.ndarray:
    return (img * 255).astype(np.uint8)


def make_single_channel(
    out_dir: Path, rng: np.random.Generator, shape=(256, 256), n_nuclei=25
) -> int:
    """Write a single-channel TIFF; return ground-truth nucleus count."""
    img, centers = _place_circles(shape, rng, n_nuclei, radius_range=(6, 12))
    img = _add_noise_and_specks(img, rng)
    path = out_dir / "synthetic_single.tif"
    tifffile.imwrite(
        path,
        _to_uint8(img),
        imagej=True,
        resolution=(1.0 / PIXEL_UM, 1.0 / PIXEL_UM),
        metadata={"unit": "um"},
    )
    return len(centers)


def make_two_channel(
    out_dir: Path, rng: np.random.Generator, shape=(256, 256), n_nuclei=20
) -> tuple[int, int, int]:
    """Write a 2-channel TIFF where ch2 partly overlaps ch1.

    Returns (count_ch0, count_ch1, n_overlapping) ground truth.
    """
    ch0, centers0 = _place_circles(shape, rng, n_nuclei, radius_range=(6, 11))

    # Channel 1: reuse a subset of ch0 centers (overlap) plus some fresh ones.
    n_overlap = n_nuclei // 2
    overlap_centers = centers0[:n_overlap]
    ch1_fresh, fresh_centers = _place_circles(
        shape, rng, n_nuclei - n_overlap, radius_range=(6, 11)
    )
    ch1, _ = _place_circles(
        shape, rng, 0, radius_range=(6, 11), centers=overlap_centers
    )
    ch1 = np.maximum(ch1, ch1_fresh)

    ch0 = _add_noise_and_specks(ch0, rng)
    ch1 = _add_noise_and_specks(ch1, rng)

    # Shape (C, H, W); ImageJ axes 'CYX'.
    stack = np.stack([_to_uint8(ch0), _to_uint8(ch1)], axis=0)
    path = out_dir / "synthetic_two_channel.tif"
    tifffile.imwrite(
        path,
        stack,
        imagej=True,
        resolution=(1.0 / PIXEL_UM, 1.0 / PIXEL_UM),
        metadata={"axes": "CYX", "unit": "um"},
    )
    return len(centers0), n_overlap + len(fresh_centers), n_overlap


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic test TIFFs.")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent,
        help="Output directory (default: this script's folder).",
    )
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    single_count = make_single_channel(args.out, rng)
    c0, c1, overlap = make_two_channel(args.out, rng)

    print("Synthetic data written to:", args.out)
    print(f"  pixel size embedded: {PIXEL_UM} um/px")
    print(f"  synthetic_single.tif      ground-truth nuclei: {single_count}")
    print(
        f"  synthetic_two_channel.tif ground-truth ch0: {c0}, ch1: {c1}, "
        f"overlapping: {overlap}"
    )


if __name__ == "__main__":
    main()
