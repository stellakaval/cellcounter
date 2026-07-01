"""Project settings: segmentation params + the live project-wide filters.

Filter-only changes (min/max µm², min circularity) recompute ``filtered_count`` across all
processed images instantly — no re-segmentation. Changing ``sensitivity``/``model_name``
would change detections themselves, so we persist the value but return
``requires_resegment`` rather than silently re-running the model over the whole project.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..db import get_session
from ..models import Project
from ..schemas import SettingsUpdate
from ..services import filters

router = APIRouter(prefix="/api/projects", tags=["settings"])

_FILTER_FIELDS = {"min_um2", "max_um2", "min_circ"}
_RESEGMENT_FIELDS = {"model_name", "sensitivity", "nms_thresh"}


@router.get("/{project_id}/settings")
def get_settings(project_id: int, session: Session = Depends(get_session)) -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    return {
        f: getattr(project, f)
        for f in (
            "model_name", "sensitivity", "nms_thresh",
            "min_um2", "max_um2", "min_circ", "edu_channel", "pdgfra_channel",
        )
    }


@router.put("/{project_id}/settings")
def update_settings(
    project_id: int, body: SettingsUpdate, session: Session = Depends(get_session)
) -> dict:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")

    changed = body.model_dump(exclude_unset=True)
    for field, value in changed.items():
        setattr(project, field, value)
    session.add(project)
    session.commit()

    requires_resegment = bool(_RESEGMENT_FIELDS & changed.keys())
    images = []
    if _FILTER_FIELDS & changed.keys():
        images = filters.recompute_project_counts(session, project_id)

    return {
        "settings": get_settings(project_id, session),
        "requires_resegment": requires_resegment,
        "images": images,
        "total": sum(i["filtered_count"] for i in images),
    }
