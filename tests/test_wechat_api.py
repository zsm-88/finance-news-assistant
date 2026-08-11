from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import Event, MarketImpact, NewsAnalysis, NewsItem, PromptVersion
from app.wechat.routes import get_session, router


@pytest.fixture
async def api_client() -> AsyncIterator[tuple[TestClient, dict[str, str]]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    ids: dict[str, str] = {}

    async with factory() as session:
        now = datetime.now(UTC)
        prompt = PromptVersion(
            prompt_name="event-analysis",
            version="m7-test",
            prompt_content="test",
            enabled=True,
        )
        high_event = Event(
            event_key="m7-high",
            title="High importance event",
            event_type="event-fallback",
            occurred_at=now,
            status="succeeded",
            importance=5,
            summary="Event summary",
        )
        low_event = Event(
            event_key="m7-low",
            title="Low importance event",
            event_type="company",
            occurred_at=now - timedelta(minutes=5),
            status="succeeded",
            importance=3,
        )
        session.add_all([prompt, high_event, low_event])
        await session.flush()

        high_news = NewsItem(
            event_id=high_event.id,
            source="cnbc",
            source_item_id="m7-high-news",
            title="Real API fixture headline",
            content="Full article content",
            url="https://example.com/news/high",
            published_at=now,
            collected_at=now,
            content_hash="a" * 64,
        )
        low_news = NewsItem(
            event_id=low_event.id,
            source="chinanews",
            source_item_id="m7-low-news",
            title="Second headline",
            content="Second article",
            published_at=now + timedelta(minutes=1),
            collected_at=now,
            content_hash="b" * 64,
        )
        session.add_all([high_news, low_news])
        await session.flush()

        session.add(
            NewsItem(
                event_id=high_event.id,
                source="chinanews",
                source_item_id="m10-high-news",
                title="真实中文财经快讯",
                content="中新网财经 RSS 摘要",
                published_at=now - timedelta(minutes=1),
                collected_at=now,
                content_hash="c" * 64,
            )
        )

        analysis = NewsAnalysis(
            event_id=high_event.id,
            news_id=high_news.id,
            prompt_version_id=prompt.id,
            provider="test-provider",
            model="test-model",
            category="macro",
            importance=5,
            summary="AI summary",
            confidence=0.9,
            raw_response={"private": "must-not-be-returned"},
            prompt_text_snapshot="private prompt",
            duration_ms=25,
        )
        session.add(analysis)
        await session.flush()
        session.add(
            MarketImpact(
                analysis_id=analysis.id,
                asset="gold",
                direction="bullish",
                confidence=0.8,
                reason="Test reason",
            )
        )
        await session.commit()
        ids["high_news"] = str(high_news.id)

    app = FastAPI()
    app.include_router(router)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, ids
    await engine.dispose()


def test_news_list_orders_filters_and_paginates(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api_client
    first = client.get("/api/v1/wechat/news", params={"page": 1, "page_size": 1})
    assert first.status_code == 200
    payload = first.json()
    assert payload["total"] == 2
    assert payload["has_more"] is True
    assert payload["items"][0]["importance"] == 3
    assert payload["items"][0]["category"] == "company"
    assert payload["items"][0]["source"] == "中新网财经"

    filtered = client.get("/api/v1/wechat/news", params={"importance": 5, "category": "macro"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1


def test_news_list_empty_and_invalid_parameters(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api_client
    empty = client.get("/api/v1/wechat/news", params={"page": 99})
    assert empty.status_code == 200
    assert empty.json()["items"] == []

    for params in ({"page": 0}, {"page_size": 101}, {"importance": 6}, {"category": ""}):
        assert client.get("/api/v1/wechat/news", params=params).status_code == 422


def test_news_detail_returns_analysis_without_sensitive_raw_data(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = api_client
    response = client.get(f"/api/v1/wechat/news/{ids['high_news']}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis"]["summary"] == "AI summary"
    assert payload["market_impacts"][0]["asset"] == "gold"
    assert "raw_response" not in payload["analysis"]
    assert "prompt_text_snapshot" not in payload["analysis"]

    missing = client.get(f"/api/v1/wechat/news/{uuid4()}")
    assert missing.status_code == 404


def test_dashboard_returns_latest_data(api_client: tuple[TestClient, dict[str, str]]) -> None:
    client, _ = api_client
    response = client.get("/api/v1/wechat/dashboard")
    assert response.status_code == 200
    payload = response.json()
    assert payload["system_status"] == "正常"
    assert len(payload["top_news"]) == 2
    assert len(payload["latest_events"]) == 2
    assert payload["generated_at"]


def test_database_exception_returns_generic_500(
    api_client: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api_client

    async def broken_session() -> AsyncIterator[AsyncSession]:
        raise RuntimeError("database-url-secret")
        yield

    client.app.dependency_overrides[get_session] = broken_session
    response = client.get("/api/v1/wechat/news")
    assert response.status_code == 500
    assert "database-url-secret" not in response.text
