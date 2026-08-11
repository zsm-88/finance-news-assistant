import os
from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Event

pytestmark = pytest.mark.integration


@pytest.fixture
async def postgres_session() -> AsyncSession:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL constraint tests")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def test_event_importance_constraint(postgres_session: AsyncSession) -> None:
    postgres_session.add(
        Event(
            event_key="invalid-importance",
            title="invalid",
            event_type="test",
            occurred_at=datetime.now(UTC),
            status="pending",
            importance=6,
        )
    )
    with pytest.raises(IntegrityError):
        await postgres_session.commit()

