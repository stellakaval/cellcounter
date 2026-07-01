"""SQLite engine + session helpers.

Single-file SQLite shared by the request handlers and the background worker thread, so
``check_same_thread=False``. The engine is created lazily against the current data root
(tests set ``$CELLCOUNTER_DATA`` before the app starts).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from . import config
from . import models  # noqa: F401 -- import so tables register on SQLModel.metadata

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = os.environ.get("DATABASE_URL", f"sqlite:///{config.db_path()}")
        if db_url.startswith("sqlite"):
            _engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            _engine = create_engine(db_url)
        SQLModel.metadata.create_all(_engine)
        _migrate(_engine)
    return _engine


def _migrate(engine) -> None:
    """Add columns that may be missing in existing DBs (forward-only, additive).

    SQLite only — Postgres gets the correct schema from create_all.
    """
    from sqlalchemy import text

    # Only run PRAGMA-based migrations on SQLite
    url_str = str(engine.url)
    if not url_str.startswith("sqlite"):
        return

    new_cols = [
        ("image",   "scene_index", "INTEGER NOT NULL DEFAULT 0"),
        ("image",   "scene_name",  "TEXT"),
        ("image",   "edu_count",   "INTEGER"),
        ("project", "nms_thresh",  "REAL NOT NULL DEFAULT 0.3"),
        ("project", "user_id",     "TEXT NOT NULL DEFAULT ''"),
    ]
    with engine.connect() as conn:
        for table, col, definition in new_cols:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {r[1] for r in rows}
            if col not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {definition}"))
        conn.commit()


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
