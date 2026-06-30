"""Per-image endpoints: table rows, record, PNG render, thumbnail, detections JSON."""

from __future__ import annotations

import json

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from cellcounter import io

from ..db import get_session
from ..models import Image
from ..schemas import Detection, DetectionsResponse, ImageRow
from ..services import rendering
from ..services.processing import _artifacts

router = APIRouter(prefix="/api", tags=["images"])


@router.get("/projects/{project_id}/images")
def list_images(
    project_id: int, session: Session = Depends(get_session)
) -> list[ImageRow]:
    images = session.exec(
        select(Image).where(Image.project_id == project_id).order_by(Image.id)
    ).all()
    return [
        ImageRow(
            id=i.id,
            filename=i.filename,
            status=i.status,
            raw_count=i.raw_count,
            filtered_count=i.filtered_count,
            review_status=i.review_status,
            width=i.width,
            height=i.height,
        )
        for i in images
    ]


@router.get("/images/{image_id}")
def get_image(image_id: int, session: Session = Depends(get_session)) -> Image:
    image = session.get(Image, image_id)
    if image is None:
        raise HTTPException(404, "image not found")
    return image


def _require_done(image: Image | None) -> Image:
    if image is None:
        raise HTTPException(404, "image not found")
    if image.status != "done":
        raise HTTPException(409, f"image not processed yet (status={image.status})")
    return image


@router.get("/images/{image_id}/render")
def render_image(
    image_id: int, channel: int | None = None, session: Session = Depends(get_session)
):
    image = _require_done(session.get(Image, image_id))
    paths = _artifacts(image.project_id, image_id)
    ch = image.dapi_channel if channel is None else channel

    if ch == image.dapi_channel and paths["render_dapi"].exists():
        return FileResponse(paths["render_dapi"], media_type="image/png")

    # Lazily render a non-DAPI channel and cache it.
    cache = paths["render_dapi"].with_name(f"render_ch{ch}.png")
    if not cache.exists():
        data = io.load_image(image.source_path)
        if ch >= data.n_channels:
            raise HTTPException(400, f"channel {ch} out of range")
        rendering.render_png(data.channel(ch), cache)
    return FileResponse(cache, media_type="image/png")


@router.get("/images/{image_id}/thumbnail")
def thumbnail(image_id: int, session: Session = Depends(get_session)):
    image = _require_done(session.get(Image, image_id))
    paths = _artifacts(image.project_id, image_id)
    thumb = paths["render_dapi"].with_name("thumb.png")
    if not thumb.exists():
        from PIL import Image as PILImage

        im = PILImage.open(paths["render_dapi"])
        im.thumbnail((256, 256))
        im.save(thumb)
    return FileResponse(thumb, media_type="image/png")


@router.get("/images/{image_id}/detections")
def detections(
    image_id: int, session: Session = Depends(get_session)
) -> DetectionsResponse:
    image = _require_done(session.get(Image, image_id))
    paths = _artifacts(image.project_id, image_id)

    props = pd.read_csv(paths["detections"])
    polys = json.loads(paths["contours"].read_text()) if paths["contours"].exists() else {}

    out: list[Detection] = []
    for r in props.itertuples():
        area = getattr(r, "area_um2", None)
        if area is not None and pd.isna(area):
            area = None
        out.append(
            Detection(
                label=int(r.label),
                cx=round(float(r.centroid_x), 1),
                cy=round(float(r.centroid_y), 1),
                area_um2=None if area is None else round(float(area), 2),
                circularity=round(float(r.circularity), 3),
                polygon=polys.get(str(int(r.label)), []),
            )
        )
    return DetectionsResponse(
        image_id=image_id,
        pixel_um=image.pixel_um,
        width=image.width,
        height=image.height,
        detections=out,
    )
