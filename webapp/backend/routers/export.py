"""Whole-project Excel export."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session

from ..auth import current_user
from ..db import get_session
from ..models import Project
from ..services import export

router = APIRouter(prefix="/api/projects", tags=["export"])


@router.get("/{project_id}/export.xlsx")
def export_xlsx(
    project_id: int,
    include_per_cell: bool = False,
    session: Session = Depends(get_session),
    user_id: str = Depends(current_user),
):
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "project not found")
    if project.user_id and project.user_id != user_id:
        raise HTTPException(403, "forbidden")

    out = Path(tempfile.gettempdir()) / f"cellcounter_project_{project_id}.xlsx"
    export.build_workbook(session, project_id, out, include_per_cell=include_per_cell)
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in project.name)
    return FileResponse(
        out,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{safe_name or 'project'}_counts.xlsx",
    )
