"""Re-apply the project-wide filters to every processed image — without re-segmenting.

This is the cheap path the live FilterPanel uses: read each image's cached per-object table
(detections.csv), run ``measure.apply_filters`` (pure row selection), and update the
``filtered_count`` cache. Milliseconds per image.

(CSV, not parquet: pyarrow's bundled Abseil collides with TensorFlow's and deadlocks
StarDist's tf.data prefetch when both load in one process — so the backend avoids pyarrow.)
"""

from __future__ import annotations

import pandas as pd
from sqlmodel import Session, select

from cellcounter import measure

from ..models import Image, Project
from .processing import _artifacts


def recompute_project_counts(session: Session, project_id: int) -> list[dict]:
    """Recompute filtered_count for all done images in the project. Returns [{id, filtered_count}]."""
    project = session.get(Project, project_id)
    images = session.exec(
        select(Image).where(Image.project_id == project_id, Image.status == "done")
    ).all()

    out: list[dict] = []
    for image in images:
        path = _artifacts(project_id, image.id)["detections"]
        if not path.exists():
            continue
        df = pd.read_csv(path)
        filtered = measure.apply_filters(
            df, image.pixel_um, project.min_um2, project.max_um2, project.min_circ
        )
        image.filtered_count = int(len(filtered))
        session.add(image)
        out.append({"id": image.id, "filtered_count": image.filtered_count})

    session.commit()
    return out
