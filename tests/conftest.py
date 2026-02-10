"""
Shared test fixtures for all tests.

Provides:
- db_engine: In-memory SQLite engine with all tables created
- db_session: SQLAlchemy session that rolls back after each test
- client: FastAPI TestClient with test database injected
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database import Base


@pytest.fixture
def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import models so metadata is registered
    import src.models  # noqa: F401

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    """Create a database session; closed after each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def client(db_session):
    """Create a FastAPI TestClient with test database injected.

    Uses a minimal app (no lifespan/scheduler) to avoid side effects.
    """
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from src.api.router import api_router
    from src.api.dependencies import get_db
    from web.app import register_exception_handlers

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()
