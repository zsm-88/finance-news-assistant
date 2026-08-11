from datetime import UTC, date, datetime

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.providers.base import ProviderResult
from app.ai.providers.registry import ProviderRegistry
from app.ai.providers.router import ProviderRouter
from app.assistant.context import AssistantContext, AssistantContextBuilder
from app.assistant.contracts import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantIntent,
    AssistantReference,
)
from app.assistant.intent import IntentClassifier
from app.assistant.repository import AssistantUsageRepository
from app.assistant.service import AssistantProviderError, FinanceAssistantService
from app.db.base import Base
from app.db.models import AIUsage, Event, MarketImpact, NewsAnalysis, NewsItem, PromptVersion
from app.db.repositories import AnalysisRepository, EventRepository, NewsRepository
from app.fund.contracts import (
    FundHistoryStatus,
    FundNavHistoryResponse,
    FundValue,
    FundWatchlistItem,
    FundWatchlistResponse,
)
from app.market.contracts import MarketListResponse, MarketQuote
from app.wechat.routes import get_assistant_service, router


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("今天A股为什么涨？", AssistantIntent.NEWS_MARKET),
        ("今天有什么新闻？", AssistantIntent.NEWS),
        ("上证指数怎么样？", AssistantIntent.MARKET),
        ("我的基金怎么样？", AssistantIntent.FUND_ANALYSIS),
    ],
)
def test_intent_classifier(message: str, expected: AssistantIntent) -> None:
    assert IntentClassifier().classify(message) is expected


def test_market_hotspot_uses_event_intent() -> None:
    assert IntentClassifier().classify("最近有哪些市场热点？") is AssistantIntent.MARKET_EVENT


class FakeMarketService:
    async def list_quotes(self) -> MarketListResponse:
        return MarketListResponse(
            items=[
                MarketQuote(
                    symbol="sh000001",
                    name="上证指数",
                    market="CN",
                    asset_type="index",
                    price=3940.0371,
                    change=39.68,
                    change_percent=1.0175,
                    timestamp=datetime(2026, 8, 7, 7, 0, 24, tzinfo=UTC),
                    market_status="weekend",
                    source="BaoStock",
                    is_delayed=True,
                    is_stale=True,
                )
            ],
            generated_at=datetime(2026, 8, 9, tzinfo=UTC),
            cache_ttl_seconds=60,
        )


class FakeFundService:
    def __init__(self, items: list | None = None, configured: bool = False) -> None:
        self.items = items or []
        self.configured = configured

    async def watchlist(self, refresh: bool = False) -> FundWatchlistResponse:
        return FundWatchlistResponse(
            items=self.items,
            provider_configured=self.configured,
            experimental_valuation_enabled=False,
            generated_at=datetime(2026, 8, 9, tzinfo=UTC),
            message=None if self.configured else "基金正式数据源未授权",
        )

    async def nav_history(
        self, code: str, history_range: str, refresh: bool = False
    ) -> FundNavHistoryResponse:
        status: FundHistoryStatus = "unauthorized"
        return FundNavHistoryResponse(
            code=code,
            range="1m",
            items=[],
            source="Tushare",
            as_of=None,
            status=status,
            message="历史净值数据源未授权",
        )


@pytest.mark.asyncio
async def test_news_market_context_contains_real_analysis_impacts_and_stale_quote() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        occurred_at = datetime(2026, 8, 7, 4, 0, tzinfo=UTC)
        prompt = PromptVersion(
            prompt_name="event-analysis", version="test", prompt_content="test", enabled=True
        )
        event = Event(
            event_key="m13-real-event",
            title="真实政策事件",
            event_type="macro",
            occurred_at=occurred_at,
            status="succeeded",
            importance=5,
        )
        session.add_all([prompt, event])
        await session.flush()
        news = NewsItem(
            event_id=event.id,
            source="chinanews",
            source_item_id="m13-news",
            title="真实中文财经新闻",
            content="官方 RSS 摘要",
            url="https://www.chinanews.com.cn/example",
            published_at=occurred_at,
            collected_at=occurred_at,
            content_hash="f" * 64,
        )
        session.add(news)
        await session.flush()
        analysis = NewsAnalysis(
            event_id=event.id,
            news_id=news.id,
            prompt_version_id=prompt.id,
            provider="test",
            model="test",
            category="macro",
            importance=5,
            summary="真实分析摘要",
            confidence=0.9,
            raw_response={},
            prompt_text_snapshot="test",
        )
        session.add(analysis)
        await session.flush()
        session.add(
            MarketImpact(
                analysis_id=analysis.id,
                asset="A股",
                direction="bullish",
                confidence=0.8,
                reason="政策可能改善预期",
            )
        )
        await session.commit()

        builder = AssistantContextBuilder(
            EventRepository(session),
            NewsRepository(session),
            AnalysisRepository(session),
            FakeMarketService(),  # type: ignore[arg-type]
            FakeFundService(),  # type: ignore[arg-type]
        )
        context = await builder.build(AssistantIntent.NEWS_MARKET, "今天A股为什么涨？")
        assert context.payload["events"][0]["summary"] == "真实分析摘要"
        assert context.payload["events"][0]["market_impacts"][0]["asset"] == "A股"
        assert context.payload["market"][0]["market_status"] == "weekend"
        assert context.payload["market"][0]["is_stale"] is True
        assert "最近交易日" in context.data_status
        assert context.payload["market"][0]["timestamp"].startswith("2026-08-07")
        assert any(ref.type == "news" for ref in context.references.values())
    await engine.dispose()


@pytest.mark.asyncio
async def test_news_after_stale_market_cutoff_cannot_be_used_as_cause() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        event = Event(
            event_key="future-event",
            title="周末发布的新闻",
            event_type="market",
            occurred_at=datetime(2026, 8, 9, 4, 0, tzinfo=UTC),
            status="pending",
        )
        session.add(event)
        await session.commit()
        builder = AssistantContextBuilder(
            EventRepository(session),
            NewsRepository(session),
            AnalysisRepository(session),
            FakeMarketService(),  # type: ignore[arg-type]
            FakeFundService(),  # type: ignore[arg-type]
        )
        context = await builder.build(AssistantIntent.NEWS_MARKET, "今天A股为什么涨？")
        assert context.payload["events"] == []
        assert "无法确认涨跌原因" in context.data_status
    await engine.dispose()


@pytest.mark.asyncio
async def test_fund_context_keeps_official_nav_and_reports_unauthorized_history() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    item = FundWatchlistItem(
        code="000001.OF",
        name="测试基金",
        source="Tushare",
        market_status="weekend",
        official_nav=FundValue(
            value=1.2845,
            source="Tushare",
            as_of=date(2026, 8, 7),
            is_estimate=False,
            is_stale=True,
        ),
        intraday_estimate=FundValue(
            value=None,
            source="实验性估值",
            as_of=None,
            is_estimate=True,
            is_stale=True,
        ),
    )
    async with factory() as session:
        builder = AssistantContextBuilder(
            EventRepository(session),
            NewsRepository(session),
            AnalysisRepository(session),
            FakeMarketService(),  # type: ignore[arg-type]
            FakeFundService([item], configured=True),  # type: ignore[arg-type]
        )
        context = await builder.build(AssistantIntent.FUND_ANALYSIS)
        fund = context.payload["funds"][0]
        assert fund["official_nav"]["value"] == 1.2845
        assert fund["official_nav"]["is_estimate"] is False
        assert fund["intraday_estimate"]["is_estimate"] is True
        assert fund["official_nav_history"]["status"] == "unauthorized"
        assert fund["official_nav_history"]["items"] == []
        assert "历史净值数据源未授权" in context.data_status
    await engine.dispose()


class FakeContextBuilder:
    async def build(
        self, intent: AssistantIntent, message: str = ""
    ) -> AssistantContext:
        reference = AssistantReference(
            type="news",
            id="real-news-id",
            title="真实新闻",
            source="中新网财经",
            published_at=datetime(2026, 8, 9, tzinfo=UTC),
        )
        return AssistantContext(
            payload={"events": [{"title": "真实新闻"}]},
            references={"news:real-news-id": reference},
            data_time=datetime(2026, 8, 9, tzinfo=UTC),
            data_status="数据正常",
        )


class FakeProvider:
    name = "openai-compatible"
    model = "test-model"

    def __init__(self, output: dict | None = None, error: Exception | None = None) -> None:
        self.output = output or {
            "answer": "根据真实数据，当前只能确认这条新闻。",
            "summary": "当前数据支持一项事实。",
            "key_points": ["真实新闻已发布"],
            "market_impacts": [],
            "reference_ids": ["news:real-news-id", "news:invented"],
            "disclaimer": "",
        }
        self.error = error

    async def analyze(self, prompt) -> ProviderResult:  # type: ignore[no-untyped-def]
        if self.error:
            raise self.error
        return ProviderResult(
            self.name,
            self.model,
            self.output,
            {},
            prompt_tokens=100,
            completion_tokens=30,
            total_tokens=130,
        )


class FakeCache:
    async def get(self, intent, message):  # type: ignore[no-untyped-def]
        return None

    async def set(self, intent, message, value):  # type: ignore[no-untyped-def]
        return None


def provider_router(provider: FakeProvider) -> ProviderRouter:
    registry = ProviderRegistry()
    registry.register(provider)
    return ProviderRouter(registry, provider.name)


@pytest.mark.asyncio
async def test_assistant_filters_invented_references_and_records_tokens() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        service = FinanceAssistantService(
            provider_router(FakeProvider()),
            FakeContextBuilder(),  # type: ignore[arg-type]
            AssistantUsageRepository(session),
            FakeCache(),  # type: ignore[arg-type]
        )
        response = await service.chat(AssistantChatRequest(message="今天有什么新闻？"))
        assert [reference.id for reference in response.references] == ["real-news-id"]
        usage = await session.scalar(select(AIUsage))
        assert usage is not None
        assert usage.purpose == "finance_assistant"
        assert usage.intent == "NEWS"
        assert usage.success is True
        assert usage.total_tokens == 130
        assert usage.analysis_id is None
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider",
    [
        FakeProvider(error=httpx.ReadTimeout("timeout")),
        FakeProvider(error=RuntimeError("rate limit")),
        FakeProvider(output={"answer": "missing required fields"}),
    ],
)
async def test_assistant_provider_failures_are_recorded(provider: FakeProvider) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        service = FinanceAssistantService(
            provider_router(provider),
            FakeContextBuilder(),  # type: ignore[arg-type]
            AssistantUsageRepository(session),
            FakeCache(),  # type: ignore[arg-type]
        )
        with pytest.raises(AssistantProviderError):
            await service.chat(AssistantChatRequest(message="今天有什么新闻？"))
        usage = await session.scalar(select(AIUsage))
        assert usage is not None
        assert usage.success is False
        assert usage.error_type
    await engine.dispose()


class FakeApiService:
    async def chat(self, request: AssistantChatRequest) -> AssistantChatResponse:
        return AssistantChatResponse(
            intent=AssistantIntent.NEWS,
            answer=f"已回答：{request.message}",
            summary="摘要",
            key_points=[],
            market_impacts=[],
            references=[],
            data_time=datetime(2026, 8, 9, tzinfo=UTC),
            data_status="数据正常",
            disclaimer="",
        )


def test_ai_chat_api_contract_and_validation() -> None:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_assistant_service] = lambda: FakeApiService()
    with TestClient(app) as client:
        response = client.post("/api/v1/wechat/ai/chat", json={"message": "今天有什么新闻？"})
        assert response.status_code == 200
        assert response.json()["intent"] == "NEWS"
        assert response.json()["answer"].startswith("已回答")
        assert client.post("/api/v1/wechat/ai/chat", json={"message": "   "}).status_code == 422
        assert client.post(
            "/api/v1/wechat/ai/chat", json={"message": "长" * 1001}
        ).status_code == 422
