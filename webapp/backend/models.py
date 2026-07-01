"""SQLModel tables: Project and Image.

Per-object detection data is NOT in the DB — it lives in parquet/JSON on disk (the access
pattern is always "all detections for one image"). The DB keeps light state: settings,
status, and the two count caches (``raw_count`` pre-filter, ``filtered_count`` after the
project-wide filters).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(default="", index=True)  # Supabase user UUID; "" = dev/legacy
    name: str
    source_folder: str = ""
    created_at: datetime = Field(default_factory=_utcnow)

    # Segmentation params (set during calibration; changing these needs a re-segment).
    model_name: str = "StarDist fluo"
    sensitivity: float = 0.5
    nms_thresh: float = 0.3   # nucleus overlap tolerance: higher = more merged, lower = more split

    # Project-wide filters (live; re-applied to cached tables without re-segmenting).
    min_um2: float = 30.0
    max_um2: float | None = None
    min_circ: float = 0.0

    # Channel assignments (which index in the acquisition corresponds to which stain).
    dapi_channel: int = 0           # which channel index is DAPI / nuclei
    edu_channel: int | None = None  # which channel index is EdU (None = no EdU)
    pdgfra_channel: int | None = None


class Image(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    filename: str
    source_path: str

    width: int | None = None
    height: int | None = None
    pixel_um: float | None = None
    n_channels: int | None = None
    channel_names: str | None = None  # JSON-encoded list
    dapi_channel: int = 0

    scene_index: int = 0           # which CZI scene (0 for non-multi-scene)
    scene_name: str | None = None  # optional label from CZI metadata

    status: str = "queued"  # queued | processing | done | error
    error: str | None = None

    raw_count: int | None = None        # nuclei detected before filters
    filtered_count: int | None = None   # after project-wide filters (cache)
    edu_count: int | None = None        # EdU+ nuclei (auto-threshold, optional)

    review_status: str = "unreviewed"   # unreviewed | approved | needs_fix
    is_calibration: bool = False
    processed_at: datetime | None = None
