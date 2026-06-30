"""Import a folder of images into a project: insert rows + enqueue for processing."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from cellcounter.batch import list_images

from ..models import Image
from .. import worker


def import_folder(
    session: Session, project_id: int, folder: str | Path, *, calibration: bool = False
) -> list[int]:
    """Add every supported image in ``folder`` to the project and enqueue it.

    Skips files already imported (by source path). Returns the new image IDs.
    """
    existing = set(
        session.exec(
            select(Image.source_path).where(Image.project_id == project_id)
        ).all()
    )

    new_ids: list[int] = []
    for path in list_images(folder):
        src = str(path.resolve())
        if src in existing:
            continue
        image = Image(
            project_id=project_id,
            filename=path.name,
            source_path=src,
            status="queued",
            is_calibration=calibration,
        )
        session.add(image)
        session.commit()
        session.refresh(image)
        new_ids.append(image.id)

    for image_id in new_ids:
        worker.enqueue(image_id)
    return new_ids
