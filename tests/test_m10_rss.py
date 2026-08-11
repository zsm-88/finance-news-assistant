from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.base import Base
from app.db.models import NewsItem, RawNews, SourceCursor
from app.db.repositories import EventRepository
from app.ingestion.contracts import RawNewsPayload
from app.ingestion.matcher import DeterministicEventMatcher
from app.ingestion.normalizer import DefaultNormalizer
from app.ingestion.rss import RssSourceAdapter
from app.ingestion.service import IngestionService
from app.runtime import DEFAULT_PROMPT, run_cycle

RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>中新网财经</title>
  <item><title>第三条：中国经济数据公布</title><link>https://www.chinanews.com.cn/cj/3.shtml</link>
    <description><![CDATA[中国经济数据保持稳定。]]></description>
    <pubDate>Sun, 09 Aug 2026 10:03:00 +0800</pubDate></item>
  <item><title>第二条：人民币汇率保持稳定</title><link>https://www.chinanews.com.cn/cj/2.shtml</link>
    <description><![CDATA[人民币市场运行平稳。]]></description>
    <pubDate>Sun, 09 Aug 2026 10:02:00 +0800</pubDate></item>
  <item><title>第一条：制造业景气回升</title><link>https://www.chinanews.com.cn/cj/1.shtml</link>
    <description><![CDATA[制造业景气水平有所回升。]]></description>
    <pubDate>Sun, 09 Aug 2026 10:01:00 +0800</pubDate></item>
</channel></rss>""".encode()


@pytest.mark.asyncio
async def test_rss_parses_chinese_fields_stable_ids_and_hashes() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=RSS_XML,
            headers={"ETag": '"feed-v1"', "Last-Modified": "Sun, 09 Aug 2026 02:03:00 GMT"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = RssSourceAdapter("chinanews", "https://example.test/finance.xml", client)
        first = await adapter.fetch()
        second = await adapter.fetch()

    assert [item.raw_json["title"] for item in first] == [
        "第一条：制造业景气回升",
        "第二条：人民币汇率保持稳定",
        "第三条：中国经济数据公布",
    ]
    assert first[0].source_item_id == "https://www.chinanews.com.cn/cj/1.shtml"
    assert first[0].source_item_id == second[0].source_item_id
    assert first[0].content_hash == second[0].content_hash
    assert first[0].source_revision == first[0].content_hash
    assert first[0].raw_json["content"] == "制造业景气水平有所回升。"
    assert first[0].raw_json["published_at"] == "2026-08-09T02:01:00+00:00"
    assert adapter.cursor_update["etag"] == '"feed-v1"'


@pytest.mark.asyncio
async def test_rss_sends_conditional_headers_and_handles_304() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["etag"] = request.headers.get("if-none-match", "")
        seen["modified"] = request.headers.get("if-modified-since", "")
        return httpx.Response(304, headers={"ETag": '"feed-v1"'})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = RssSourceAdapter("chinanews", "https://example.test/finance.xml", client)
        result = await adapter.fetch(
            {
                "etag": '"feed-v1"',
                "last_modified": "Sun, 09 Aug 2026 02:03:00 GMT",
                "feed_drained": True,
            }
        )

    assert result == []
    assert seen == {
        "etag": '"feed-v1"',
        "modified": "Sun, 09 Aug 2026 02:03:00 GMT",
    }
    assert adapter.cursor_update["last_status_code"] == 304


@pytest.mark.asyncio
async def test_rss_incremental_cursor_idempotency_and_entry_update() -> None:
    current_xml = RSS_XML
    request_headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_headers.append(request.headers)
        if request.headers.get("if-none-match") == '"feed-v1"':
            return httpx.Response(304, headers={"ETag": '"feed-v1"'})
        return httpx.Response(
            200,
            content=current_xml,
            headers={"ETag": '"feed-v1"', "Last-Modified": "Sun, 09 Aug 2026 02:03:00 GMT"},
        )

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = RssSourceAdapter("chinanews", "https://example.test/finance.xml", client)
        async with factory() as session:
            service = IngestionService(
                session,
                adapter,
                DefaultNormalizer(),
                DeterministicEventMatcher(EventRepository(session)),
            )
            assert len(await service.ingest(limit=2)) == 2
            await session.commit()
            cursor = await session.scalar(
                select(SourceCursor).where(SourceCursor.source == "chinanews")
            )
            assert cursor is not None
            assert cursor.last_id == "https://www.chinanews.com.cn/cj/2.shtml"
            assert cursor.cursor_data["feed_drained"] is False

            assert len(await service.ingest(limit=2)) == 1
            await session.commit()
            await session.refresh(cursor)
            assert cursor.last_id == "https://www.chinanews.com.cn/cj/3.shtml"
            assert cursor.cursor_data["feed_drained"] is True
            assert "if-none-match" not in request_headers[1]

            assert await service.ingest(limit=2) == []
            await session.commit()
            assert request_headers[2]["if-none-match"] == '"feed-v1"'
            assert await session.scalar(select(func.count(NewsItem.id))) == 3
            assert await session.scalar(select(func.count(RawNews.id))) == 3

            current_xml = RSS_XML.replace(
                "中国经济数据保持稳定。".encode(),
                "中国经济数据保持稳定，最新修订已发布。".encode(),
            )
            cursor.cursor_data = {**cursor.cursor_data, "etag": '"feed-v0"'}
            await session.commit()
            assert len(await service.ingest(limit=2)) == 1
            await session.commit()
            updated = await session.scalar(
                select(NewsItem).where(
                    NewsItem.source_item_id == "https://www.chinanews.com.cn/cj/3.shtml"
                )
            )
            assert updated is not None
            assert "最新修订" in updated.content
            assert await session.scalar(select(func.count(NewsItem.id))) == 3
            assert await session.scalar(select(func.count(RawNews.id))) == 4
    await engine.dispose()


def test_chinese_ai_prompt_requires_simplified_chinese_output() -> None:
    assert "简体中文" in DEFAULT_PROMPT
    assert "summary" in DEFAULT_PROMPT
    assert "market_impacts.reason" in DEFAULT_PROMPT


@pytest.mark.asyncio
async def test_source_failure_isolated_and_cnbc_fallback_continues(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    async def fake_fetch(self, cursor=None):  # type: ignore[no-untyped-def]
        if self.name == "chinanews":
            raise httpx.ConnectError("primary source unavailable")
        received_at = datetime.now(UTC)
        return [
            RawNewsPayload(
                source="cnbc",
                source_item_id="fallback-1",
                raw_json={
                    "title": "CNBC international fallback",
                    "content": "Fallback remains available.",
                    "published_at": received_at.isoformat(),
                },
                headers={},
                received_at=received_at,
                content_hash="f" * 64,
                fetch_version="cnbc-rss-v1",
            )
        ]

    monkeypatch.setattr(RssSourceAdapter, "fetch", fake_fetch)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        enable_crawler=True,
        enable_ai=False,
        enable_push=False,
        enable_chinanews=True,
        enable_tmtpost=False,
        enable_jin10=False,
        enable_cnbc_fallback=True,
        max_items_per_cycle=3,
    )
    async with factory() as session:
        assert await run_cycle(session, None, settings) == 1
        assert await session.scalar(select(func.count(NewsItem.id))) == 1
        fallback = await session.scalar(select(NewsItem))
        assert fallback is not None and fallback.source == "cnbc"
    await engine.dispose()
