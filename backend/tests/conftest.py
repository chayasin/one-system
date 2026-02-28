"""
Shared pytest fixtures.

Uses an in-memory SQLite database (via aiosqlite) so tests run without a
live Postgres instance.  The SQLite dialect supports most of our schema;
UUID columns are stored as strings.

Environment overrides are applied before importing app modules so that
Settings() picks up the test database URL.
"""
import os
import uuid

# Set test environment BEFORE importing any app module
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DEV_SKIP_AUTH", "true")
os.environ.setdefault("LOCAL_DB_HOST", "")  # will be overridden by fixture
os.environ.setdefault("COGNITO_USER_POOL_ID", "")
os.environ.setdefault("COGNITO_APP_CLIENT_ID", "")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import event

from app.models.base import Base
from app.models.user import User  # noqa: F401 — registers model
from app.models.reference import RefServiceType, RefComplaintType, RefClosureReason  # noqa: F401
from app.models.sla import SlaConfig  # noqa: F401
from app.models.case import Case, CaseHistory, CaseAttachment  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.sequence import CaseSequence  # noqa: F401
from app.models.summary import SummaryCasesDaily  # noqa: F401


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
    )

    # SQLite doesn't enforce FK by default — enable it
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine):
    """Provide a transactional test session that rolls back after each test."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> User:
    """Create and return a persisted ADMIN user."""
    user = User(
        cognito_user_id=str(uuid.uuid4()),
        full_name="Test Admin",
        email="admin@test.local",
        role="ADMIN",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def officer_user(db_session: AsyncSession) -> User:
    """Create and return a persisted OFFICER user."""
    user = User(
        cognito_user_id=str(uuid.uuid4()),
        full_name="Test Officer",
        email="officer@test.local",
        role="OFFICER",
        responsible_province="กรุงเทพมหานคร",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def client(engine, db_session: AsyncSession, admin_user: User):
    """
    AsyncClient for the FastAPI app with:
    - DB dependency overridden to use the test session
    - DEV_SKIP_AUTH=true so requests are authenticated as admin_user
      by default (pass X-Dev-User-ID header with a different cognito_user_id
      to switch users).
    """
    from app.main import app
    from app.core.db import get_db

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"X-Dev-User-ID": admin_user.cognito_user_id},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
