"""Phase 0 — model validation gate (throwaway diagnostic, not product code).

Runs BOTH pretrained backends (Cellpose-SAM and StarDist 2D_versatile_fluo) on every
image in a folder, renders a 3-panel figure (original | StarDist | Cellpose) per image
with the detected count, and prints a comparison table. Each backend is wrapped so a
missing/broken backend is reported rather than crashing the whole run.

Decision the gate informs (report, do NOT decide silently):
  - If a model's overlays look clean on the user's REAL images -> use it as default,
    no fine-tuning needed.
  - If both look poor -> recommend Phase 3 fine-tuning.

Usage:
    python scripts/phase0_validate.py                 # uses sample_data/ (synthetic)
    python scripts/phase0_validate.py --folder PATH   # point at real images later

Synthetic ground-truth counts (from sample_data/make_synthetic.py) are matched by
filename so the table can show expected vs detected.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import tifffile

# Ground-truth counts for the synthetic files (channel 0 is what the diagnostic runs on).
SYNTHETIC_GROUND_TRUTH = {
    "synthetic_single.tif": 25,
    "synthetic_two_channel.tif": 20,  # channel 0
}

IMAGE_EXTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".czi"}

# Which channel holds the nuclei stain to count. For these samples channel 0 is DAPI.
DAPI_CHANNEL = 0


def load_2d(path: Path) -> tuple[np.ndarray, float | None]:
    """Load an image and reduce to a single 2D nuclei plane for the diagnostic.

    Returns (2D float32 array, pixel_um or None). Multi-channel/stacked inputs are
    reduced to the nuclei channel (DAPI = channel 0); Z-stacks are max-projected.
    """
    ext = path.suffix.lower()
    if ext == ".czi":
        return _load_czi_2d(path)
    arr = tifffile.imread(path) if ext in {".tif", ".tiff"} else _imread_any(path)
    arr = np.asarray(arr)
    while arr.ndim > 2:
        # Heuristic: if last axis is small (<=4) it's likely RGB(A) -> mean over it.
        if arr.shape[-1] <= 4 and arr.ndim == 3:
            arr = arr.mean(axis=-1)
        else:
            arr = arr[0]
    return arr.astype(np.float32), None


def _load_czi_2d(path: Path) -> tuple[np.ndarray, float | None]:
    """Read a Zeiss CZI: select the DAPI channel, max-project Z, return (2D, pixel_um)."""
    import re

    import czifile

    with czifile.CziFile(path) as czi:
        arr = np.asarray(czi.asarray())
        axes = list(czi.axes)  # e.g. "HTCZYX0"
        meta = czi.metadata()

    # Max-project a Z-stack (good for nuclei counting), then pick the DAPI channel,
    # then collapse every remaining non-spatial axis by taking index 0.
    if "Z" in axes:
        zi = axes.index("Z")
        arr = arr.max(axis=zi)
        axes.pop(zi)
    if "C" in axes:
        ci = axes.index("C")
        idx = [slice(None)] * arr.ndim
        idx[ci] = min(DAPI_CHANNEL, arr.shape[ci] - 1)
        arr = arr[tuple(idx)]
        axes.pop(ci)
    for ax in list(axes):
        if ax not in ("Y", "X"):
            i = axes.index(ax)
            idx = [slice(None)] * arr.ndim
            idx[i] = 0
            arr = arr[tuple(idx)]
            axes.pop(i)

    # Pixel size: CZI stores X/Y scaling in metres/pixel.
    pixel_um = None
    m = re.search(r"<Distance Id=\"X\">\s*<Value>([0-9.eE+-]+)</Value>", meta)
    if m:
        pixel_um = float(m.group(1)) * 1e6  # m -> um
    return arr.astype(np.float32), pixel_um


def _imread_any(path: Path) -> np.ndarray:
    from skimage.io import imread

    return imread(path)


def count_labels(labels: np.ndarray) -> int:
    """Number of distinct nonzero label IDs."""
    if labels is None:
        return 0
    uniq = np.unique(labels)
    return int((uniq != 0).sum())


def run_stardist(img2d: np.ndarray):
    """Return (labels, count) or (None, error_string)."""
    try:
        from csbdeep.utils import normalize
        from stardist.models import StarDist2D
    except Exception as e:  # noqa: BLE001
        return None, f"StarDist unavailable: {e}"
    try:
        print("  [StarDist] loading 2D_versatile_fluo (downloads weights on first run)...")
        model = StarDist2D.from_pretrained("2D_versatile_fluo")
        labels, _ = model.predict_instances(normalize(img2d))
        return labels, count_labels(labels)
    except Exception as e:  # noqa: BLE001
        return None, f"StarDist failed: {e}"


def run_cellpose(img2d: np.ndarray):
    """Return (labels, count) or (None, error_string). Uses Cellpose-SAM (v4 API)."""
    try:
        import torch
        from cellpose import models
    except Exception as e:  # noqa: BLE001
        return None, f"Cellpose unavailable: {e}"
    try:
        use_gpu = bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available())
        print(f"  [Cellpose] loading CellposeModel (gpu/mps={use_gpu}; downloads weights on first run)...")
        model = models.CellposeModel(gpu=use_gpu)
        out = model.eval(img2d)  # v4 CellposeModel.eval -> (masks, flows, styles)
        masks = out[0]
        return masks, count_labels(masks)
    except Exception as e:  # noqa: BLE001
        return None, f"Cellpose failed: {e}"


def render_figure(img2d, sd_labels, sd_count, cp_labels, cp_count, out_path: Path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from skimage.color import label2rgb

    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    axes[0].imshow(img2d, cmap="gray")
    axes[0].set_title("original")

    if sd_labels is not None:
        axes[1].imshow(label2rgb(sd_labels, bg_label=0))
        axes[1].set_title(f"StarDist: {sd_count} cells")
    else:
        axes[1].text(0.5, 0.5, "StarDist\nunavailable", ha="center", va="center")
        axes[1].set_title("StarDist: n/a")

    if cp_labels is not None:
        axes[2].imshow(label2rgb(cp_labels, bg_label=0))
        axes[2].set_title(f"Cellpose: {cp_count} cells")
    else:
        axes[2].text(0.5, 0.5, "Cellpose\nunavailable", ha="center", va="center")
        axes[2].set_title("Cellpose: n/a")

    for ax in axes:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 0 model validation.")
    default_folder = Path(__file__).resolve().parents[1] / "sample_data"
    parser.add_argument("--folder", type=Path, default=default_folder)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "phase0_results",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=0,
        help="If >0, validate an evenly-spaced sample of this many images (avoids "
        "running every file in a large folder). 0 = all.",
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    images = sorted(
        p for p in args.folder.iterdir() if p.suffix.lower() in IMAGE_EXTS
    )
    if not images:
        raise SystemExit(f"No images found in {args.folder}")

    total = len(images)
    if args.max and args.max < total:
        step = total / args.max
        picked = [images[int(i * step)] for i in range(args.max)]
        skipped = total - len(picked)
        print(
            f"Phase 0: sampling {len(picked)} of {total} images (evenly spaced); "
            f"{skipped} not validated this run.\n"
        )
        images = picked
    else:
        print(f"Phase 0: validating {total} image(s) from {args.folder}\n")

    rows = []
    for path in images:
        print(f"Image: {path.name}")
        img2d, pixel_um = load_2d(path)
        if pixel_um:
            print(f"    pixel size: {pixel_um:.4f} um/px; shape: {img2d.shape}")

        sd_labels, sd_res = run_stardist(img2d)
        sd_count = sd_res if sd_labels is not None else None
        if sd_labels is None:
            print(f"    {sd_res}")

        cp_labels, cp_res = run_cellpose(img2d)
        cp_count = cp_res if cp_labels is not None else None
        if cp_labels is None:
            print(f"    {cp_res}")

        fig_path = args.out / f"{path.stem}_phase0.png"
        render_figure(img2d, sd_labels, sd_count, cp_labels, cp_count, fig_path)

        gt = SYNTHETIC_GROUND_TRUTH.get(path.name)
        rows.append((path.name, sd_count, cp_count, gt))
        print(f"    -> figure: {fig_path}\n")

    # Summary table.
    print("=" * 64)
    print(f"{'image':<28}{'stardist':>10}{'cellpose':>10}{'truth':>10}")
    print("-" * 64)
    for name, sd, cp, gt in rows:
        print(
            f"{name:<28}{_fmt(sd):>10}{_fmt(cp):>10}{_fmt(gt):>10}"
        )
    print("=" * 64)
    print(
        "\nGate: figures saved to phase0_results/. The default-model and fine-tuning\n"
        "decision is DEFERRED until real images are validated "
        "(re-run with --folder <real images>)."
    )


def _fmt(v) -> str:
    return "n/a" if v is None else str(v)


if __name__ == "__main__":
    main()
