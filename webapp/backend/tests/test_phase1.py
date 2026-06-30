"""Phase 1 backend verification — pure logic, real-CZI pipeline, and HTTP endpoints.

Pointed at a temp data root (via $CELLCOUNTER_DATA) and the real sample .czi files. The
StarDist model loads once per process, so segmentation cost is paid by the first test only.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[3]
SAMPLES = REPO / "sample_data" / "cellsamples"


@pytest.fixture()
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CELLCOUNTER_DATA", str(tmp_path))
    from webapp.backend import db

    db.reset_engine()
    yield tmp_path
    db.reset_engine()


def _smallest_samples(n: int = 1) -> list[Path]:
    """Smallest .czi files (~512², ~948 KB) — StarDist is slow, so verification uses these,
    not the 96 MB 2586² APOE image which takes minutes per segmentation on CPU."""
    files = sorted(SAMPLES.glob("*.czi"), key=lambda p: p.stat().st_size)
    if len(files) < n:
        pytest.skip("not enough sample .czi files present")
    return files[:n]


def _first_sample() -> Path:
    return _smallest_samples(1)[0]


# --- pure logic ---------------------------------------------------------------------------


def test_contours_df_shapes_and_bounds():
    from cellcounter import measure

    labels = np.zeros((40, 40), dtype=np.int32)
    labels[5:15, 5:15] = 1
    labels[20:35, 22:38] = 2
    df = measure.contours_df(labels)

    assert list(df["label"]) == [1, 2]
    for poly in df["polygon"]:
        arr = np.array(poly)
        assert arr.ndim == 2 and arr.shape[1] == 2
        assert arr[:, 0].min() >= 0 and arr[:, 0].max() <= 40  # x in bounds
        assert arr[:, 1].min() >= 0 and arr[:, 1].max() <= 40  # y in bounds

    assert measure.contours_df(np.zeros((10, 10), dtype=np.int32)).empty


# --- real-CZI pipeline --------------------------------------------------------------------


def _make_project_with_image(folder: Path, src: Path):
    from sqlmodel import Session

    from webapp.backend.db import get_engine
    from webapp.backend.models import Image, Project

    with Session(get_engine()) as s:
        project = Project(name="t", source_folder=str(folder))
        s.add(project)
        s.commit()
        s.refresh(project)
        image = Image(
            project_id=project.id, filename=src.name, source_path=str(src.resolve())
        )
        s.add(image)
        s.commit()
        s.refresh(image)
        return project.id, image.id


def test_process_real_czi(data_root):
    from sqlmodel import Session

    from webapp.backend.db import get_engine
    from webapp.backend.models import Image
    from webapp.backend.services import processing
    from webapp.backend.services.processing import _artifacts

    src = _first_sample()
    project_id, image_id = _make_project_with_image(SAMPLES, src)

    processing.process_image(image_id)

    with Session(get_engine()) as s:
        image = s.get(Image, image_id)
        assert image.status == "done", image.error
        assert image.raw_count and image.raw_count > 0
        assert image.filtered_count is not None
        assert image.width and image.height

    paths = _artifacts(project_id, image_id)
    for key in ("labels", "detections", "contours", "render_dapi", "meta"):
        assert paths[key].exists(), f"missing artifact: {key}"

    # contours are within image bounds
    import json

    polys = json.loads(paths["contours"].read_text())
    assert len(polys) > 0
    any_poly = next(iter(polys.values()))
    arr = np.array(any_poly)
    assert arr[:, 0].max() <= image.width and arr[:, 1].max() <= image.height


def test_model_loads_once(data_root):
    """Processing two images keeps the same cached StarDist model (no reload)."""
    from cellcounter import segment
    from webapp.backend.services import processing

    files = _smallest_samples(2)

    project_id, id1 = _make_project_with_image(SAMPLES, files[0])
    _, id2 = _make_project_with_image(SAMPLES, files[1])

    processing.process_image(id1)
    model_after_first = segment._STARDIST_MODEL
    assert model_after_first is not None

    processing.process_image(id2)
    assert segment._STARDIST_MODEL is model_after_first  # same object, not reloaded


# --- HTTP endpoints -----------------------------------------------------------------------


def test_endpoints_flow(data_root):
    from fastapi.testclient import TestClient

    from webapp.backend.app import app
    from webapp.backend.services import processing

    client = TestClient(app)  # no `with` -> background worker is not started

    r = client.post("/api/projects", json={"name": "demo", "source_folder": str(SAMPLES)})
    assert r.status_code == 200, r.text
    project_id = r.json()["id"]

    r = client.post(f"/api/projects/{project_id}/import", json={})
    assert r.status_code == 200, r.text
    image_ids = r.json()["image_ids"]
    assert len(image_ids) > 0

    # process the SMALLEST image synchronously (fast + deterministic), not the 96MB APOE one
    smallest_name = _smallest_samples(1)[0].name
    rows = client.get(f"/api/projects/{project_id}/images").json()
    target = next(row["id"] for row in rows if row["filename"] == smallest_name)
    processing.process_image(target)

    rows = client.get(f"/api/projects/{project_id}/images").json()
    assert any(row["status"] == "done" and row["filtered_count"] is not None for row in rows)

    det = client.get(f"/api/images/{target}/detections").json()
    assert det["image_id"] == target
    assert len(det["detections"]) > 0
    d0 = det["detections"][0]
    assert {"label", "cx", "cy", "circularity", "polygon"} <= set(d0)

    png = client.get(f"/api/images/{target}/render")
    assert png.status_code == 200 and png.headers["content-type"] == "image/png"

    status = client.get(f"/api/projects/{project_id}/status").json()
    assert status["done"] >= 1
