"""FastAPI application: starts the background worker on startup and mounts the routers."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from . import worker
from .db import get_engine
from .routers import export, images, projects, review, settings

_FRONTEND_DIST = Path(__file__).parent.parent.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_engine()  # create the DB + tables
    worker.start_worker()
    _resume_queued()  # re-enqueue any jobs that were pending when the server last stopped
    yield


def _resume_queued() -> None:
    """On startup, reset 'processing' → 'queued' (they were interrupted) and enqueue all queued images."""
    from sqlmodel import Session, select
    from .models import Image
    with Session(get_engine()) as session:
        stuck = session.exec(select(Image).where(Image.status == "processing")).all()
        for img in stuck:
            img.status = "queued"
            session.add(img)
        if stuck:
            session.commit()
        pending = session.exec(select(Image.id).where(Image.status == "queued")).all()
    for image_id in pending:
        worker.enqueue(image_id)


app = FastAPI(title="cellcounter web", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

_allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:4173"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router)
app.include_router(images.router)
app.include_router(settings.router)
app.include_router(review.router)
app.include_router(export.router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


# Serve the built React frontend when dist/ exists (production / integrated mode).
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
