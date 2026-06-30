"""FastAPI application: starts the background worker on startup and mounts the routers."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from . import worker
from .db import get_engine
from .routers import export, images, projects, review, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_engine()  # create the DB + tables
    worker.start_worker()
    yield


app = FastAPI(title="cellcounter web", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(projects.router)
app.include_router(images.router)
app.include_router(settings.router)
app.include_router(review.router)
app.include_router(export.router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}
