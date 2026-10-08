"""
PriceSense database connection and session handling.

This module owns the SQLite engine and session factory. It intentionally
keeps all connection/engine state isolated here so the rest of the
application (and tests) never construct engines or sessions directly.

Design notes:
- `init_db()` (re)creates the engine bound to a SQLite file and ensures all
  tables exist. It defaults to the path from `config.DATABASE_PATH`, but
  accepts an explicit path so tests can point at an isolated, disposable
  database file instead of the real application database.
- `get_session()` is a context manager yielding a SQLAlchemy `Session`. It
  commits on success and rolls back on error, always closing the session
  afterwards.
- Foreign key enforcement is turned on explicitly, since SQLite disables it
  by default.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import config
from database.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Ensure SQLite enforces FOREIGN KEY constraints (off by default)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db(db_path: str | Path | None = None) -> Engine:
    """
    Initialize the database: (re)create the engine and ensure all tables exist.

    Args:
        db_path: Optional path to the SQLite file. Defaults to
            `config.DATABASE_PATH`. Primarily overridden in tests to use an
            isolated, temporary database file.

    Returns:
        The SQLAlchemy Engine bound to the database file.
    """
    global _engine, _SessionLocal

    path = Path(db_path) if db_path is not None else config.DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{path}", future=True)
    event.listen(engine, "connect", _enable_foreign_keys)

    Base.metadata.create_all(engine)

    _engine = engine
    _SessionLocal = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
    )
    return engine


def get_engine() -> Engine:
    """Return the current engine, initializing the default database if needed."""
    if _engine is None:
        init_db()
    assert _engine is not None  # for type checkers
    return _engine


@contextmanager
def get_session() -> Iterator[Session]:
    """
    Provide a transactional SQLAlchemy session as a context manager.

    Commits on successful exit, rolls back on exception, and always closes
    the session. Initializes the default database on first use if it has
    not been explicitly initialized yet.
    """
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None  # for type checkers

    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
