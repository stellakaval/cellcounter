"""Save/load a session: the (possibly hand-edited) label image + all parameters.

Lets the user stop and resume, and makes a result reproducible. Labels are stored as a
TIFF (lossless integer) and parameters as JSON, in a chosen directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

_LABELS_NAME = "labels.tif"
_PARAMS_NAME = "params.json"


def save_session(folder: str | Path, labels: np.ndarray, params: dict) -> Path:
    """Write ``labels.tif`` + ``params.json`` into ``folder`` (created if needed)."""
    import tifffile

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(folder / _LABELS_NAME, np.asarray(labels).astype(np.int32))
    (folder / _PARAMS_NAME).write_text(json.dumps(params, indent=2, default=str))
    return folder


def load_session(folder: str | Path) -> tuple[np.ndarray, dict]:
    """Read back ``(labels, params)`` from a session folder."""
    import tifffile

    folder = Path(folder)
    labels = np.asarray(tifffile.imread(folder / _LABELS_NAME)).astype(np.int32)
    params = json.loads((folder / _PARAMS_NAME).read_text())
    return labels, params
