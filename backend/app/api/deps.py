"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.llm.base import LlmProvider
from app.llm.factory import get_provider


def db_session() -> Iterator[Session]:
    yield from get_db()


def llm_provider() -> LlmProvider:
    return get_provider()


__all__ = ["db_session", "llm_provider"]
