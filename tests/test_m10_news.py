from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Event, NewsItem, RawNews, SourceCursor
from app.db.repositories import EventRepository
from app.ingestion.contracts import RawNewsPayload
from app.ingestion.jin10 import Jin10Adapter, Jin10NotConfiguredError
from app.ingestion.matcher import DeterministicEventMatcher
from app.ingestion.normalizer import DefaultNormalizer
from app.ingestion.service import IngestionService


@pytest.mark.asyncio
async def test_jin10_official_adapter_uses_secret_header_and_incremental_cursor() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["secret"] = request.headers.get("secret-key", "")
        seen["last_id"] = request.url.params.get("last_id", "")
        seen["category"] = request.url.params.get("category", "")
        return httpx.Response(
            200,
            json={
                "code": 200,
                "data": [
                    {
                        "id": 9001,
                        "time": "2026-08-09 09:31:00",
                        "important": 1,
                        "data": {"content": "中国7月CPI同比上涨"},
                    }
                ],
            },
            headers={"x-request-id": "request-1"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = Jin10Adapter("test-secret", "https://open-data-api.jin10.com/data-api", 1, client)
        payloads = await adapter.fetch({"last_id": "8999"})

    assert seen == {"secret": "test-secret", "last_id": "8999", "category": "1"}
    assert payloads[0].source_item_id == "9001"
    assert payloads[0].raw_json["data"] == {"content": "中国7月CPI同比上涨"}
    assert "secret-key" not in payloads[0].headers
    normalized = DefaultNormalizer().normalize(payloads[0])
    assert normalized.title == "中国7月CPI同比上涨"
    assert normalized.published_at.tzinfo == UTC


def test_jin10_missing_secret_is_explicit() -> None:
    with pytest.raises(Jin10NotConfiguredError, match="金十数据源未配置"):
        Jin10Adapter("", "https://open-data-api.jin10.com/data-api")


class RevisionAdapter:
    name = "jin10"

    def __init__(self) -> None:
        self.call = 0

    async def fetch(self, cursor=None):  # type: ignore[no-untyped-def]
        self.call += 1
        action = ("created", "updated", "deleted")[self.call - 1]
        content = "央行宣布降准" if self.call == 1 else "央行宣布下调存款准备金率"
        return [
            RawNewsPayload(
                source="jin10",
                source_item_id="42",
                raw_json={
                    "id": 42,
                    "time": "2026-08-09 10:00:00",
                    "data": {"content": content},
                },
                headers={},
                received_at=datetime.now(UTC),
                content_hash=str(self.call) * 64,
                fetch_version="jin10-open-platform-v1",
                source_revision=f"r{self.call}",
                source_action=action,
            )
        ]


@pytest.mark.asyncio
async def test_ingestion_preserves_revisions_updates_and_deletes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    adapter = RevisionAdapter()
    async with factory() as session:
        service = IngestionService(
            session,
            adapter,
            DefaultNormalizer(),
            DeterministicEventMatcher(EventRepository(session)),
        )
        assert len(await service.ingest()) == 1
        await session.commit()
        assert len(await service.ingest()) == 1
        await session.commit()
        assert await service.ingest() == []
        await session.commit()

        assert await session.scalar(select(func.count(RawNews.id))) == 3
        news = await session.scalar(select(NewsItem).where(NewsItem.source_item_id == "42"))
        assert news is not None
        assert news.title == "央行宣布下调存款准备金率"
        assert news.deleted_at is not None
        cursor = await session.scalar(select(SourceCursor).where(SourceCursor.source == "jin10"))
        assert cursor is not None and cursor.last_id == "42"
    await engine.dispose()


@pytest.mark.asyncio
async def test_event_matcher_merges_similar_cross_source_headlines() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        now = datetime.now(UTC)
        event = Event(
            event_key="existing-cpi-event",
            title="美国7月CPI同比上涨3.0%",
            event_type="macro",
            occurred_at=now - timedelta(minutes=10),
            status="pending",
        )
        session.add(event)
        await session.flush()
        payload = RawNewsPayload(
            source="jin10",
            source_item_id="cpi-2",
            raw_json={"content": "金十数据：美国7月CPI同比升至3.0%", "time": now.isoformat()},
            headers={},
            received_at=now,
            content_hash="x" * 64,
            fetch_version="v1",
        )
        normalized = DefaultNormalizer().normalize(payload)
        matcher = DeterministicEventMatcher(EventRepository(session))
        assert await matcher.match(normalized) == "existing-cpi-event"
    await engine.dispose()
