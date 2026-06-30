"""SQLite engine + session helpers.

Single-file SQLite shared by the request handlers and the background worker thread, so
``check_same_thread=False``. The engine is created lazily against the current data root
(tests set ``$CELLCOUNTER_DATA`` before the app starts).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from . import config
from . import models  # noqa: F401 -- import so tables register on SQLModel.metadata

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            f"sqlite:///{config.db_path()}",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(_engine)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (tests call this after pointing at a fresh data root)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session bound to the shared engine."""
    with Session(get_engine()) as session:
        yield session
