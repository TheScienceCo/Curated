"""Engine / session lifecycle."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # StaticPool + check_same_thread=False lets an in-memory test DB be
        # shared across the TestClient's threads.
        from sqlalchemy.pool import StaticPool

        return {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


def init_engine(url: str | None = None) -> Engine:
    """Create the process-wide engine and session factory.

    Idempotent when called without an explicit URL: repeated calls (the app
    lifespan, a script, a test) reuse the existing engine rather than throwing
    away its connection pool. Passing a URL always replaces the engine, which
    is how tests bind to an in-memory database.
    """
    global _engine, _SessionLocal
    if url is None and _engine is not None:
        return _engine
    resolved = url or settings.sqlalchemy_url
    _engine = create_engine(resolved, future=True, **_engine_kwargs(resolved))
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    logger.info(
        "Database engine initialised (%s)", _engine.url.render_as_string(hide_password=True)
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        return init_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional scope for scripts and background work."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_all() -> None:
    from app.db import models  # noqa: F401  (ensure models are imported/registered)
    from app.db.base import Base

    Base.metadata.create_all(bind=get_engine())
