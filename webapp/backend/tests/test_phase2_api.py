"""Fast Phase 2 API tests — no StarDist.

We fabricate a "done" image by writing a tiny detections.parquet + meta directly, so the
settings/filters/review/export endpoints are exercised in well under a second.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest


@pytest.fixture()
def data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CELLCOUNTER_DATA", str(tmp_path))
    from webapp.backend import db

    db.reset_engine()
    yield tmp_path
    db.reset_engine()


def _fake_done_project(pixel_um=0.5):
    """Create a project + one done image with three detections of areas 10/40/90 µm²."""
    from sqlmodel import Session

    from webapp.backend import config
    from webapp.backend.db import get_engine
    from webapp.backend.models import Image, Project
    from webapp.backend.services.processing import _artifacts

    with Session(get_engine()) as s:
        project = Project(name="demo", min_um2=0.0)
        s.add(project)
        s.commit()
        s.refresh(project)
        image = Image(
            project_id=project.id, filename="fake.czi", source_path="/x/fake.czi",
            status="done", pixel_um=pixel_um, width=100, height=100, raw_count=3,
            filtered_count=3,
        )
        s.add(image)
        s.commit()
        s.refresh(image)
        pid, iid = project.id, image.id

    df = pd.DataFrame(
        {
            "label": [1, 2, 3],
            "centroid_x": [10.0, 50.0, 90.0],
            "centroid_y": [10.0, 50.0, 90.0],
            "area_px": [40.0, 160.0, 360.0],
            "area_um2": [10.0, 40.0, 90.0],  # at pixel_um=0.5: px*0.25
            "perimeter": [22.0, 45.0, 67.0],
            "circularity": [0.9, 0.8, 0.7],
        }
    )
    paths = _artifacts(pid, iid)
    df.to_csv(paths["detections"], index=False)
    paths["contours"].write_text(json.dumps({"1": [[8, 8], [12, 12]]}))
    paths["meta"].write_text(json.dumps({"pixel_um": pixel_um, "width": 100, "height": 100}))
    return pid, iid


def test_settings_filter_recompute(data_root):
    from fastapi.testclient import TestClient

    from webapp.backend.app import app

    pid, iid = _fake_done_project()
    client = TestClient(app)

    # min_um2=35 should drop the 10 µm² detection -> 2 survive
    r = client.put(f"/api/projects/{pid}/settings", json={"min_um2": 35.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["requires_resegment"] is False
    assert body["images"] == [{"id": iid, "filtered_count": 2}]
    assert body["total"] == 2

    # the cache is persisted
    rows = client.get(f"/api/projects/{pid}/images").json()
    assert rows[0]["filtered_count"] == 2

    # tightening further to 50 µm² -> only the 90 survives
    r = client.put(f"/api/projects/{pid}/settings", json={"min_um2": 50.0})
    assert r.json()["total"] == 1

    # changing sensitivity flags a needed re-segment and does NOT recompute filters
    r = client.put(f"/api/projects/{pid}/settings", json={"sensitivity": 0.8})
    assert r.json()["requires_resegment"] is True


def test_settings_matches_apply_filters(data_root):
    """The endpoint's recompute must equal measure.apply_filters on the same table."""
    from fastapi.testclient import TestClient

    from cellcounter import measure
    from webapp.backend.app import app
    from webapp.backend.services.processing import _artifacts

    pid, iid = _fake_done_project()
    client = TestClient(app)
    client.put(f"/api/projects/{pid}/settings", json={"min_um2": 20.0, "min_circ": 0.75})

    df = pd.read_csv(_artifacts(pid, iid)["detections"])
    expected = len(measure.apply_filters(df, 0.5, 20.0, None, 0.75))
    rows = client.get(f"/api/projects/{pid}/images").json()
    assert rows[0]["filtered_count"] == expected


def test_review_status_and_progress(data_root):
    from fastapi.testclient import TestClient

    from webapp.backend.app import app

    pid, iid = _fake_done_project()
    client = TestClient(app)

    r = client.put(f"/api/images/{iid}/review", json={"review_status": "approved"})
    assert r.status_code == 200 and r.json()["review_status"] == "approved"

    r = client.put(f"/api/images/{iid}/review", json={"review_status": "bogus"})
    assert r.status_code == 400

    prog = client.get(f"/api/projects/{pid}/review-progress").json()
    assert prog == {"total": 1, "unreviewed": 0, "approved": 1, "needs_fix": 0}


def test_export_xlsx_structure(data_root):
    from fastapi.testclient import TestClient

    from webapp.backend.app import app

    pid, _ = _fake_done_project()
    client = TestClient(app)

    r = client.get(f"/api/projects/{pid}/export.xlsx", params={"include_per_cell": True})
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]

    import io as _io

    xls = pd.ExcelFile(_io.BytesIO(r.content))
    assert set(xls.sheet_names) == {"Summary", "Cells"}
    summary = xls.parse("Summary")
    assert len(summary) == 1
    assert summary.iloc[0]["image"] == "fake.czi"
    assert summary.iloc[0]["nucleus_count"] == 3
    cells = xls.parse("Cells")
    assert len(cells) == 3 and "image" in cells.columns


def test_models_endpoint(data_root):
    from fastapi.testclient import TestClient

    from webapp.backend.app import app

    client = TestClient(app)
    r = client.get("/api/models")
    assert r.status_code == 200
    assert isinstance(r.json()["models"], list) and len(r.json()["models"]) >= 1
