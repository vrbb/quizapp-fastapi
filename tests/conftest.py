from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.database  # noqa: F401  (registers the SQLite foreign-key listener)
import app.models  # noqa: F401  (registers all models on Base.metadata)
from app.database import Base


@pytest.fixture
def engine():
    """Fresh in-memory SQLite DB per test; StaticPool shares one connection across threads."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine) -> Generator[Session, None, None]:
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with TestingSession() as session:
        yield session


class FailingEmailSender:
    """Always fails; records how many times it was called."""

    def __init__(self) -> None:
        self.calls = 0

    def send(self, message) -> None:
        self.calls += 1
        raise ConnectionError("SMTP server down")


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def email_sender():
    """Recording mock sender that always succeeds. Tests may swap the override."""
    from app.services.email_service import MockEmailSender

    return MockEmailSender(failure_rate=0.0)


@pytest.fixture
def client(engine, session_factory, email_sender):
    """TestClient wired to the in-memory DB.

    Not used as a context manager, so the app lifespan (which seeds the real
    quizapp.db) does not run; tests seed explicitly via the `seeded` fixture.
    """
    from fastapi.testclient import TestClient

    from app.database import get_db, get_session_factory
    from app.main import app
    from app.services.email_service import get_email_sender

    def override_get_db():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_email_sender] = lambda: email_sender
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(db):
    from app.seed import seed_quizzes

    seed_quizzes(db)
    return db


def collect_keys(data) -> set[str]:
    """All dict keys at any depth of a JSON payload."""
    if isinstance(data, dict):
        return set(data) | {k for v in data.values() for k in collect_keys(v)}
    if isinstance(data, list):
        return {k for item in data for k in collect_keys(item)}
    return set()
