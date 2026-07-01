"""Project CRUD + folder import + status polling."""

from __future__ import annotations

import shutil
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, func, select

from .. import config, worker
from ..auth import current_user
from ..db import get_session
from ..models import Image, Project
from ..schemas import ImportRequest, ProjectCreate, ProjectSummary, StatusResponse
from ..services import ingest

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _require_project(project_id: int, user_id: str, session: Session) -> Project:
    p = session.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "project not found")
    # Allow access if project has no user_id set (legacy/dev data)
    if p.user_id and p.user_id != user_id:
        raise HTTPException(403, "forbidden")
    return p


@router.post("")
def create_project(
    body: ProjectCreate,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> Project:
    project = Project(name=body.name, source_folder=body.source_folder or "", user_id=user_id)
    for field in ("model_name", "sensitivity", "nms_thresh", "min_um2", "max_um2", "min_circ", "dapi_channel", "edu_channel"):
        val = getattr(body, field)
        if val is not None:
            setattr(project, field, val)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("")
def list_projects(
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> list[ProjectSummary]:
    projects = session.exec(
        select(Project)
        .where((Project.user_id == user_id) | (Project.user_id == ""))
        .order_by(Project.id)
    ).all()
    out = []
    for p in projects:
        n_images = session.exec(
            select(func.count()).select_from(Image).where(Image.project_id == p.id)
        ).one()
        n_done = session.exec(
            select(func.count())
            .select_from(Image)
            .where(Image.project_id == p.id, Image.status == "done")
        ).one()
        out.append(
            ProjectSummary(
                id=p.id,
                name=p.name,
                created_at=p.created_at.isoformat(),
                n_images=n_images,
                n_done=n_done,
            )
        )
    return out


@router.get("/{project_id}")
def get_project(
    project_id: int,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> Project:
    return _require_project(project_id, user_id, session)


class ProjectRename(BaseModel):
    name: str


@router.put("/{project_id}/name")
def rename_project(
    project_id: int,
    body: ProjectRename,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> Project:
    project = _require_project(project_id, user_id, session)
    project.name = body.name.strip()
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.delete("/{project_id}/images/{image_id}")
def delete_image(
    project_id: int,
    image_id: int,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> dict:
    _require_project(project_id, user_id, session)
    image = session.get(Image, image_id)
    if image is None or image.project_id != project_id:
        raise HTTPException(404, "image not found")
    session.delete(image)
    session.commit()
    shutil.rmtree(config.project_dir(project_id) / "renders" / str(image_id), ignore_errors=True)
    return {"deleted": image_id}


@router.delete("/{project_id}")
def delete_project(
    project_id: int,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> dict:
    project = _require_project(project_id, user_id, session)
    for image in session.exec(select(Image).where(Image.project_id == project_id)).all():
        session.delete(image)
    session.delete(project)
    session.commit()
    shutil.rmtree(config.project_dir(project_id), ignore_errors=True)
    return {"deleted": project_id}


@router.post("/{project_id}/import")
def import_folder(
    project_id: int,
    body: ImportRequest,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> dict:
    project = _require_project(project_id, user_id, session)
    folder = body.folder or project.source_folder
    if not folder:
        raise HTTPException(400, "no folder given and project has no source_folder")
    new_ids = ingest.import_folder(session, project_id, folder, dapi_channel=project.dapi_channel)
    return {"added": len(new_ids), "image_ids": new_ids}


@router.post("/{project_id}/upload")
async def upload_files(
    project_id: int,
    files: List[UploadFile],
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> dict:
    """Accept browser-uploaded .czi/.tif files, save to uploads dir, enqueue processing."""
    project = _require_project(project_id, user_id, session)

    upload_dir = config.project_dir(project_id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    SUPPORTED = {".czi", ".tif", ".tiff"}
    MAX_BYTES = 300 * 1024 * 1024  # 300 MB per file
    CHUNK = 256 * 1024  # 256 KB chunks — keeps memory flat regardless of file size
    saved = []
    for f in files:
        suffix = "." + f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if suffix not in SUPPORTED:
            continue
        dest = upload_dir / f.filename
        size = 0
        try:
            with dest.open("wb") as out:
                while True:
                    chunk = await f.read(CHUNK)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        out.close()
                        dest.unlink(missing_ok=True)
                        raise HTTPException(413, f"{f.filename} exceeds 300 MB limit")
                    out.write(chunk)
        except HTTPException:
            raise
        except Exception as exc:
            dest.unlink(missing_ok=True)
            raise HTTPException(500, f"Failed to save {f.filename}: {exc}") from exc
        saved.append(dest)

    if not saved:
        raise HTTPException(400, "no supported files (.czi/.tif/.tiff) in upload")

    new_ids = ingest.import_folder(session, project_id, upload_dir, dapi_channel=project.dapi_channel)
    return {"added": len(new_ids), "image_ids": new_ids}


@router.post("/{project_id}/rerun")
def rerun_project(
    project_id: int,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> dict:
    """Re-queue all images in a project for re-segmentation (model/sensitivity changed)."""
    _require_project(project_id, user_id, session)
    images = session.exec(select(Image).where(Image.project_id == project_id)).all()
    for img in images:
        img.status = "queued"
        img.raw_count = None
        img.filtered_count = None
        img.edu_count = None
        img.error = None
        session.add(img)
    session.commit()
    for img in images:
        worker.enqueue(img.id)
    return {"requeued": len(images)}


@router.get("/{project_id}/status")
def project_status(
    project_id: int,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> StatusResponse:
    _require_project(project_id, user_id, session)
    images = session.exec(select(Image).where(Image.project_id == project_id)).all()
    counts = {"queued": 0, "processing": 0, "done": 0, "error": 0}
    for img in images:
        counts[img.status] = counts.get(img.status, 0) + 1
    return StatusResponse(
        total=len(images),
        **counts,
        images=[
            {
                "id": i.id,
                "status": i.status,
                "raw_count": i.raw_count,
                "filtered_count": i.filtered_count,
            }
            for i in images
        ],
    )
