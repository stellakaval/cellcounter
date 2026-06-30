"""Filesystem layout + data root for the web app.

Everything the app persists lives under one data root (default ``~/.cellcounter_web``,
overridable with ``$CELLCOUNTER_DATA`` — the tests point this at a temp dir). The SQLite
file holds light state; heavy artifacts (label images, detection tables, rendered PNGs)
live on disk under ``projects/{pid}/images/{iid}/`` and are referenced by path.
"""

from __future__ import annotations

import os
from pathlib import Path


def data_root() -> Path:
    """Root dir for the DB + per-project artifacts (created on demand)."""
    root = Path(os.environ.get("CELLCOUNTER_DATA", Path.home() / ".cellcounter_web"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def db_path() -> Path:
    return data_root() / "cellcounter.db"


def project_dir(project_id: int) -> Path:
    d = data_root() / "projects" / str(project_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def image_dir(project_id: int, image_id: int) -> Path:
    d = project_dir(project_id) / "images" / str(image_id)
    d.mkdir(parents=True, exist_ok=True)
    return d
