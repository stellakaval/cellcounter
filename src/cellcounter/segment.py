"""Unified segmentation model registry (StarDist default; Cellpose optional).

Exposes a tiny API the widget and batch code call:

    list_models() -> ["StarDist fluo", ("Cellpose-SAM" if weights present)]
    segment(image2d, model_name, sensitivity, pixel_um) -> int label image

Design choices (see docs/research_notes.md):
- **StarDist is the default** — validated on the real DAPI data, runs on Apple Silicon, and
  its weights are reachable here. Cellpose-SAM is offered only when its weights already exist
  locally (HuggingFace is network-blocked on the target machine).
- One ``sensitivity`` knob (0..1, higher = more cells) maps per-backend to the right threshold.
- Images are auto-rescaled toward ~0.5 µm/px for StarDist (its training resolution); skipping
  this silently under-detects on finely-sampled images.
- Each backend is lazy-imported and failures degrade gracefully (model dropped, no crash).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

STARDIST = "StarDist fluo"
CELLPOSE = "Cellpose-SAM"

# StarDist 2D_versatile_fluo is trained around this pixel size.
STARDIST_TARGET_UM = 0.5
# Cellpose weights cache (only present if the user placed them there).
_CELLPOSE_WEIGHTS = Path.home() / ".cellpose" / "models" / "cpsam_v2"


def list_models() -> list[str]:
    """Available models on this machine. StarDist always; Cellpose only if weights exist."""
    models = []
    if _stardist_available():
        models.append(STARDIST)
    if _cellpose_available():
        models.append(CELLPOSE)
    return models or [STARDIST]  # always offer StarDist as the labelled default


def segment(
    image2d: np.ndarray,
    model_name: str = STARDIST,
    sensitivity: float = 0.5,
    pixel_um: float | None = None,
) -> np.ndarray:
    """Segment a single 2D channel into an int label image (0 = background, 1..N = cells)."""
    if model_name == CELLPOSE:
        return _segment_cellpose(image2d, sensitivity)
    return _segment_stardist(image2d, sensitivity, pixel_um)


# --- StarDist ---------------------------------------------------------------------------

_STARDIST_MODEL = None  # cached across calls (weights load is slow)


def _stardist_available() -> bool:
    try:
        import stardist  # noqa: F401
        import tensorflow  # noqa: F401
    except Exception:
        return False
    return True


def _get_stardist():
    global _STARDIST_MODEL
    if _STARDIST_MODEL is None:
        from stardist.models import StarDist2D

        _STARDIST_MODEL = StarDist2D.from_pretrained("2D_versatile_fluo")
    return _STARDIST_MODEL


def _segment_stardist(
    image2d: np.ndarray, sensitivity: float, pixel_um: float | None
) -> np.ndarray:
    from csbdeep.utils import normalize

    model = _get_stardist()
    img = normalize(image2d.astype(np.float32), 1, 99.8)

    # Higher sensitivity -> lower probability threshold -> more detections.
    prob_thresh = float(np.clip(0.7 - 0.6 * sensitivity, 0.05, 0.95))
    # Rescale toward the model's training resolution (shrinks finely-sampled images).
    scale = (pixel_um / STARDIST_TARGET_UM) if pixel_um else None
    labels, _ = model.predict_instances(
        img,
        prob_thresh=prob_thresh,
        nms_thresh=0.3,
        scale=scale,
        n_tiles=_guess_n_tiles(img.shape),
    )
    return labels.astype(np.int32)


def _guess_n_tiles(shape, tile: int = 1024) -> tuple[int, int]:
    """Tile large images so prediction fits in memory; (1, 1) for small ones."""
    h, w = shape[:2]
    return (max(1, -(-h // tile)), max(1, -(-w // tile)))


# --- Cellpose (optional) ----------------------------------------------------------------

_CELLPOSE_MODEL = None


def _cellpose_available() -> bool:
    if not _CELLPOSE_WEIGHTS.exists():
        return False
    try:
        import cellpose  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    return True


def _segment_cellpose(image2d: np.ndarray, sensitivity: float) -> np.ndarray:
    global _CELLPOSE_MODEL
    import torch
    from cellpose import models

    if _CELLPOSE_MODEL is None:
        use_gpu = bool(
            getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
        )
        _CELLPOSE_MODEL = models.CellposeModel(gpu=use_gpu)
    # Higher sensitivity -> lower cellprob threshold -> more detections.
    cellprob = float(np.clip(2.0 - 4.0 * sensitivity, -6.0, 6.0))
    masks = _CELLPOSE_MODEL.eval(image2d, cellprob_threshold=cellprob)[0]
    return np.asarray(masks).astype(np.int32)
