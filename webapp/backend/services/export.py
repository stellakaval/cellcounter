"""Export a whole project's counts to .xlsx (pandas + openpyxl).

Summary sheet: one row per image (filename, counts, review status, pixel size) plus the
project settings the counts were produced with. Optional per-cell sheet: every surviving
detection across all images (after the current project filters), tagged with its image.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlmodel import Session, select

from cellcounter import measure

from ..models import Image, Project
from .processing import _artifacts


def build_workbook(
    session: Session, project_id: int, out_path: str | Path, *, include_per_cell: bool = False
) -> Path:
    project = session.get(Project, project_id)
    if project is None:
        raise ValueError("project not found")
    images = session.exec(
        select(Image).where(Image.project_id == project_id).order_by(Image.id)
    ).all()

    summary_rows = []
    per_cell_frames = []
    for image in images:
        summary_rows.append(
            {
                "image": image.filename,
                "nucleus_count": image.filtered_count,
                "raw_count": image.raw_count,
                "review_status": image.review_status,
                "status": image.status,
                "pixel_um": image.pixel_um,
                "model": project.model_name,
                "sensitivity": project.sensitivity,
                "min_um2": project.min_um2,
                "max_um2": project.max_um2,
                "min_circ": project.min_circ,
            }
        )
        if include_per_cell and image.status == "done":
            path = _artifacts(project_id, image.id)["detections"]
            if path.exists():
                df = measure.apply_filters(
                    pd.read_parquet(path), image.pixel_um,
                    project.min_um2, project.max_um2, project.min_circ,
                )
                df = df.copy()
                df.insert(0, "image", image.filename)
                per_cell_frames.append(df)

    out_path = Path(out_path)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Summary", index=False)
        if include_per_cell:
            cells = (
                pd.concat(per_cell_frames, ignore_index=True)
                if per_cell_frames
                else pd.DataFrame()
            )
            cells.to_excel(writer, sheet_name="Cells", index=False)
    return out_path
