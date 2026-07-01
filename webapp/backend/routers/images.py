"""Per-image endpoints: table rows, record, PNG render, thumbnail, detections JSON, corrections."""

from __future__ import annotations

import json

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from cellcounter import io

from ..db import get_session
from ..models import Image, Project
from ..schemas import Detection, DetectionsResponse, ImageRow
from ..services import rendering
from ..services.processing import _artifacts

_EMPTY_CORRECTIONS = {"deleted": [], "added": []}


class CorrectionsBody(BaseModel):
    deleted: list[int]            # AI detection labels removed from DAPI count
    added: list[dict]             # manually placed DAPI points: {id, cx, cy}
    added_edu: list[dict] = []   # manually placed EdU-only points: {id, cx, cy}
    deleted_edu: list[int] = []  # AI detections marked as NOT EdU+ (still in DAPI count)

router = APIRouter(prefix="/api", tags=["images"])


@router.get("/projects/{project_id}/images")
def list_images(
    project_id: int, session: Session = Depends(get_session)
) -> list[ImageRow]:
    images = session.exec(
        select(Image).where(Image.project_id == project_id).order_by(Image.id)
    ).all()
    rows = []
    for i in images:
        ch_names = None
        if i.channel_names:
            try:
                ch_names = json.loads(i.channel_names)
            except Exception:
                pass
        rows.append(
            ImageRow(
                id=i.id,
                filename=i.filename,
                status=i.status,
                raw_count=i.raw_count,
                filtered_count=i.filtered_count,
                edu_count=i.edu_count,
                review_status=i.review_status,
                width=i.width,
                height=i.height,
                scene_index=i.scene_index,
                scene_name=i.scene_name,
                n_channels=i.n_channels,
                channel_names=ch_names,
                dapi_channel=i.dapi_channel,
            )
        )
    return rows


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
        data = io.load_image(image.source_path, scene_index=image.scene_index)
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

    # Lazy EdU measurement for images processed before this feature was added
    edu_threshold: float | None = None
    if paths["meta"].exists():
        meta = json.loads(paths["meta"].read_text())
        edu_threshold = meta.get("edu_threshold")

        if "edu_ratio" not in props.columns and meta.get("markers") and paths["labels"].exists():
            markers = meta.get("markers", {})
            edu_ch = markers.get("EdU")
            if edu_ch is not None:
                import numpy as np
                import tifffile
                from cellcounter import compare
                from skimage.filters import threshold_otsu
                labels = tifffile.imread(paths["labels"])
                data = io.load_image(image.source_path, scene_index=image.scene_index)
                dapi_idx = meta.get("dapi_channel", 0)
                edu_channel = data.channel(int(edu_ch))
                dapi_channel = data.channel(int(dapi_idx))
                edu_means = compare.marker_intensity(labels, edu_channel)
                dapi_means = compare.marker_intensity(labels, dapi_channel)
                edu_vals = edu_means["intensity_mean"].to_numpy()
                dapi_vals = dapi_means["intensity_mean"].to_numpy()
                edu_ratio = edu_vals / (dapi_vals + 1e-6)
                props = props.merge(
                    edu_means.rename(columns={"intensity_mean": "edu_mean"}),
                    on="label", how="left",
                )
                ratio_df = edu_means[["label"]].copy()
                ratio_df["edu_ratio"] = edu_ratio
                props = props.merge(ratio_df, on="label", how="left")
                props.to_csv(paths["detections"], index=False)
                if len(edu_ratio) > 1 and not np.allclose(edu_ratio, edu_ratio[0]):
                    edu_threshold = float(threshold_otsu(edu_ratio))
                    edu_count = int((edu_ratio > edu_threshold).sum())
                elif len(edu_ratio) > 1:
                    edu_threshold = float(np.median(edu_ratio))
                    edu_count = int((edu_ratio > edu_threshold).sum())
                else:
                    edu_threshold = None
                    edu_count = None
                meta["edu_threshold"] = edu_threshold
                meta["edu_count"] = edu_count
                paths["meta"].write_text(json.dumps(meta, default=str))
                image.edu_count = edu_count
                session.add(image)
                session.commit()

    out: list[Detection] = []
    for r in props.itertuples():
        area = getattr(r, "area_um2", None)
        if area is not None and pd.isna(area):
            area = None
        def _safe_float(val):
            if val is None: return None
            try:
                f = float(val)
                return None if pd.isna(f) else f
            except (TypeError, ValueError):
                return None
        edu_mean_val = _safe_float(getattr(r, "edu_mean", None))
        edu_ratio_val = _safe_float(getattr(r, "edu_ratio", None))
        out.append(
            Detection(
                label=int(r.label),
                cx=round(float(r.centroid_x), 1),
                cy=round(float(r.centroid_y), 1),
                area_um2=None if area is None else round(float(area), 2),
                circularity=round(float(r.circularity), 3),
                polygon=polys.get(str(int(r.label)), []),
                edu_mean=None if edu_mean_val is None else round(edu_mean_val, 2),
                edu_ratio=None if edu_ratio_val is None else round(edu_ratio_val, 4),
            )
        )
    return DetectionsResponse(
        image_id=image_id,
        pixel_um=image.pixel_um,
        width=image.width,
        height=image.height,
        detections=out,
        edu_threshold=edu_threshold,
    )


@router.get("/images/{image_id}/corrections")
def get_corrections(image_id: int, session: Session = Depends(get_session)) -> dict:
    image = _require_done(session.get(Image, image_id))
    path = _artifacts(image.project_id, image_id)["corrections"]
    if not path.exists():
        return _EMPTY_CORRECTIONS
    return json.loads(path.read_text())


@router.put("/images/{image_id}/corrections")
def put_corrections(
    image_id: int, body: CorrectionsBody, session: Session = Depends(get_session)
) -> dict:
    image = _require_done(session.get(Image, image_id))
    paths = _artifacts(image.project_id, image_id)
    paths["corrections"].write_text(json.dumps({
        "deleted": body.deleted, "added": body.added,
        "added_edu": body.added_edu, "deleted_edu": body.deleted_edu,
    }))

    # Recompute filtered_count with corrections applied
    project = session.get(Project, image.project_id)
    props = pd.read_csv(paths["detections"])
    deleted_set = set(body.deleted)
    min_um2 = project.min_um2 if project else None
    max_um2 = project.max_um2 if project else None
    min_circ = project.min_circ if project else None

    passing = 0
    for r in props.itertuples():
        if int(r.label) in deleted_set:
            continue
        area = getattr(r, "area_um2", None)
        circ = float(getattr(r, "circularity", 0) or 0)
        if min_um2 is not None and area is not None and not pd.isna(float(area)) and float(area) < min_um2:
            continue
        if max_um2 is not None and area is not None and not pd.isna(float(area)) and float(area) > max_um2:
            continue
        if min_circ is not None and circ < min_circ:
            continue
        passing += 1

    passing += len(body.added)
    image.filtered_count = passing

    # Recompute edu_count if we have EdU ratio data
    if paths["meta"].exists() and "edu_ratio" in props.columns:
        import numpy as np
        meta = json.loads(paths["meta"].read_text())
        edu_threshold = meta.get("edu_threshold")
        if edu_threshold is not None:
            deleted_edu_set = set(body.deleted_edu)
            edu_count = 0
            for r in props.itertuples():
                if int(r.label) in deleted_set:
                    continue
                if int(r.label) in deleted_edu_set:
                    continue
                area = getattr(r, "area_um2", None)
                circ = float(getattr(r, "circularity", 0) or 0)
                if min_um2 is not None and area is not None and not pd.isna(float(area)) and float(area) < min_um2:
                    continue
                if max_um2 is not None and area is not None and not pd.isna(float(area)) and float(area) > max_um2:
                    continue
                if min_circ is not None and circ < min_circ:
                    continue
                try:
                    ratio = float(getattr(r, "edu_ratio", None) or 0)
                    if not np.isnan(ratio) and ratio > edu_threshold:
                        edu_count += 1
                except (TypeError, ValueError):
                    pass
            edu_count += len(body.added_edu)
            image.edu_count = edu_count

    session.add(image)
    session.commit()

    return {"ok": True, "filtered_count": passing}
