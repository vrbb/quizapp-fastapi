"""SQLAlchemy engine, session factory, declarative base and the FastAPI DB dependency."""
import sqlite3
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def _build_engine(url: str) -> Engine:
    connect_args = {}
    if url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a thread pool, so a connection may be used
        # by a different thread than the one that created it.
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, echo=settings.sql_echo)


engine = _build_engine(settings.database_url)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite ignores FOREIGN KEY constraints unless enabled per connection."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# expire_on_commit=False: objects stay usable after commit (e.g. when building
# responses or handing IDs to background tasks) without surprise lazy reloads.
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed.

    Services own commits explicitly; on any unhandled error the session is rolled back.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Importing the models package registers them on Base.metadata."""
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session_factory() -> sessionmaker[Session]:
    """FastAPI dependency for code that outlives the request (background tasks).

    Background tasks must open their own session; overriding this in tests points
    them at the test database.
    """
    return SessionLocal
