"""Pytest configuration and fixtures for backend test suite."""
import os
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings


@pytest.fixture(scope="session")
def test_engine():
    """Create a test engine with NullPool so no stale connection state leaks across tests."""
    if os.environ.get("TALENTSCREEN_TEST_DB_ISOLATED") != "1" or not os.environ.get("DATABASE_URL"):
        pytest.fail(
            "Database tests require TALENTSCREEN_TEST_DB_ISOLATED=1 and an explicit DATABASE_URL "
            "pointing to a disposable, isolated database; never use the project's .env database."
        )
    settings = get_settings()
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    return engine


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    return async_sessionmaker(
        bind=test_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )


@pytest.fixture(autouse=True)
def override_get_db(test_session_factory):
    """Automatically override FastAPI get_db dependency so app uses NullPool test session factory."""
    from app.db.session import get_db
    from app.main import app

    async def _test_get_db():
        async with test_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _test_get_db
    yield
    app.dependency_overrides.pop(get_db, None)
