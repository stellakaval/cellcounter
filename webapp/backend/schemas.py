"""Request/response models for the API (kept separate from the SQLModel tables)."""

from __future__ import annotations

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    source_folder: str = ""
    model_name: str | None = None
    sensitivity: float | None = None
    min_um2: float | None = None
    max_um2: float | None = None
    min_circ: float | None = None


class ProjectSummary(BaseModel):
    id: int
    name: str
    created_at: str
    n_images: int
    n_done: int


class ImportRequest(BaseModel):
    folder: str | None = None  # defaults to project.source_folder


class ImageRow(BaseModel):
    id: int
    filename: str
    status: str
    raw_count: int | None
    filtered_count: int | None
    review_status: str
    width: int | None
    height: int | None


class Detection(BaseModel):
    label: int
    cx: float
    cy: float
    area_um2: float | None
    circularity: float
    polygon: list[list[int]]


class DetectionsResponse(BaseModel):
    image_id: int
    pixel_um: float | None
    width: int | None
    height: int | None
    detections: list[Detection]


class StatusResponse(BaseModel):
    total: int
    queued: int
    processing: int
    done: int
    error: int
    images: list[dict]


class SettingsUpdate(BaseModel):
    model_name: str | None = None
    sensitivity: float | None = None
    min_um2: float | None = None
    max_um2: float | None = None
    min_circ: float | None = None
    edu_channel: int | None = None
    pdgfra_channel: int | None = None


class ReviewUpdate(BaseModel):
    review_status: str  # unreviewed | approved | needs_fix
