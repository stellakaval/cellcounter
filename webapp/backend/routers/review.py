"""Per-image review status (Gradescope flow) + project review progress + model list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from cellcounter import segment

from ..auth import current_user
from ..db import get_session
from ..models import Image, Project
from ..schemas import ReviewUpdate

router = APIRouter(prefix="/api", tags=["review"])

_VALID = {"unreviewed", "approved", "needs_fix"}


def _check_image_owner(image: Image, user_id: str, session: Session) -> None:
    project = session.get(Project, image.project_id)
    if project and project.user_id and project.user_id != user_id:
        raise HTTPException(403, "forbidden")


@router.put("/images/{image_id}/review")
def set_review(
    image_id: int,
    body: ReviewUpdate,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> Image:
    if body.review_status not in _VALID:
        raise HTTPException(400, f"review_status must be one of {sorted(_VALID)}")
    image = session.get(Image, image_id)
    if image is None:
        raise HTTPException(404, "image not found")
    _check_image_owner(image, user_id, session)
    image.review_status = body.review_status
    session.add(image)
    session.commit()
    session.refresh(image)
    return image


@router.get("/projects/{project_id}/review-progress")
def review_progress(
    project_id: int,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
) -> dict:
    project = session.get(Project, project_id)
    if project and project.user_id and project.user_id != user_id:
        raise HTTPException(403, "forbidden")
    images = session.exec(select(Image).where(Image.project_id == project_id)).all()
    counts = {"unreviewed": 0, "approved": 0, "needs_fix": 0}
    for img in images:
        counts[img.review_status] = counts.get(img.review_status, 0) + 1
    return {"total": len(images), **counts}


@router.get("/models")
def list_models() -> dict:
    return {"models": segment.list_models()}
