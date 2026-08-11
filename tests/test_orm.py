from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Event, MarketImpact, NewsAnalysis
from app.db.repositories import EventRepository


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as value:
        yield value
    await engine.dispose()


@pytest.mark.asyncio
async def test_repository_persists_uuid_and_utc_event(session: AsyncSession) -> None:
    event = Event(
        event_key="cpi-us-2026-08",
        title="US CPI",
        event_type="macro",
        occurred_at=datetime.now(UTC),
        status="pending",
    )
    repository = EventRepository(session)
    await repository.add(event)
    await session.commit()

    loaded = await repository.get(event.id)
    assert loaded is not None
    assert isinstance(loaded.id, UUID)
    assert loaded.deleted_at is None
    assert loaded.created_at.tzinfo is not None


def test_constraints_are_declared() -> None:
    constraints = {constraint.name for constraint in Event.__table__.constraints}
    assert "uq_events_event_key" in constraints
    assert "ck_event_importance" in constraints
    assert "ck_analysis_importance" in {c.name for c in NewsAnalysis.__table__.constraints}
    assert "ck_impact_direction" in {c.name for c in MarketImpact.__table__.constraints}
