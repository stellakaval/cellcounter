"""Project CRUD + folder import + status polling."""

from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, func, select

from .. import config
from ..db import get_session
from ..models import Image, Project
from ..schemas import ImportRequest, ProjectCreate, ProjectSummary, StatusResponse
from ..services import ingest

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.post("")
def create_project(body: ProjectCreate, session: Session = Depends(get_session)) -> Project:
    project = Project(name=body.name, source_folder=body.source_folder)
    for field in ("model_name", "sensitivity", "min_um2", "max_um2", "min_circ"):
        val = getattr(body, field)
        if val is not None:
            setattr(project, field, val)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@router.get("")
def list_projects(session: Session = Depends(get_session)) -> list[ProjectSummary]:
    projects = session.exec(select(Project).order_by(Project.id)).all()
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
def get_project(project_id: int, session: Session = Depends(get_session)) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return project


@router.delete("/{project_id}")
def delete_project(project_id: int, session: Session = Depends(get_session)) -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    for image in session.exec(select(Image).where(Image.project_id == project_id)).all():
        session.delete(image)
    session.delete(project)
    session.commit()
    shutil.rmtree(config.project_dir(project_id), ignore_errors=True)
    return {"deleted": project_id}


@router.post("/{project_id}/import")
def import_folder(
    project_id: int, body: ImportRequest, session: Session = Depends(get_session)
) -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    folder = body.folder or project.source_folder
    if not folder:
        raise HTTPException(400, "no folder given and project has no source_folder")
    new_ids = ingest.import_folder(session, project_id, folder)
    return {"added": len(new_ids), "image_ids": new_ids}


@router.get("/{project_id}/status")
def project_status(
    project_id: int, session: Session = Depends(get_session)
) -> StatusResponse:
    images = session.exec(select(Image).where(Image.project_id == project_id)).all()
    counts = {"queued": 0, "processing": 0, "done": 0, "error": 0}
    for img in images:
        counts[img.status] = counts.get(img.status, 0) + 1
    return StatusResponse(
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
