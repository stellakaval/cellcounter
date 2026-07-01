"""Import a folder of images into a project: insert rows + enqueue for processing."""

from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, select

from cellcounter.batch import list_images
from cellcounter.io import count_scenes

from ..models import Image
from .. import worker


def import_folder(
    session: Session, project_id: int, folder: str | Path, *, calibration: bool = False
) -> list[int]:
    """Add every supported image in ``folder`` to the project and enqueue it.

    CZI files with multiple scenes are fanned out into one Image row per scene.
    Skips (source_path, scene_index) pairs already imported. Returns new image IDs.
    """
    existing = set(
        session.exec(
            select(Image.source_path, Image.scene_index).where(Image.project_id == project_id)
        ).all()
    )

    new_ids: list[int] = []
    for path in list_images(folder):
        src = str(path.resolve())
        n_scenes = count_scenes(path)
        for scene_idx in range(n_scenes):
            if (src, scene_idx) in existing:
                continue
            filename = path.name if n_scenes == 1 else f"{path.stem} [Scene {scene_idx + 1}]{path.suffix}"
            image = Image(
                project_id=project_id,
                filename=filename,
                source_path=src,
                scene_index=scene_idx,
                scene_name=f"Scene {scene_idx + 1}" if n_scenes > 1 else None,
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
