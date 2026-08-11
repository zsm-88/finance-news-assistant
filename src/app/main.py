from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from .admin.router import router as admin_router
from .ai.providers.openai_compatible import OpenAICompatibleAdapter
from .ai.providers.registry import ProviderRegistry
from .ai.providers.router import ProviderRouter
from .assistant.cache import AssistantCache
from .config import get_settings
from .db.session import Infrastructure
from .fund.providers import (
    EastmoneyExperimentalFundProvider,
    EastmoneyFundValuationProvider,
    FallbackFundProvider,
    FallbackFundValuationProvider,
    SinaFundValuationProvider,
    TushareFundProvider,
)
from .fund.repository import FundCacheRepository
from .logging import configure_logging
from .market.providers import BaoStockHistoricalMarketProvider, YahooFinanceProvider
from .market.repository import MarketCacheRepository, MarketHistoryCacheRepository
from .market.service import MarketHistoryService, MarketService
from .wechat.routes import router as wechat_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    app.state.infrastructure = Infrastructure(settings)
    market_client = httpx.AsyncClient(
        timeout=settings.market_request_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "FinanceAssistant/1.0 (personal market dashboard)"},
    )
    history_provider = BaoStockHistoricalMarketProvider()
    app.state.market_service = MarketService(
        YahooFinanceProvider(
            market_client,
            base_url=settings.market_data_source_url,
        ),
        MarketCacheRepository(
            app.state.infrastructure.redis,
            ttl_seconds=settings.market_cache_ttl_seconds,
        ),
        history_provider=history_provider,
    )
    app.state.market_history_service = MarketHistoryService(
        history_provider,
        MarketHistoryCacheRepository(
            app.state.infrastructure.redis,
            ttl_seconds=settings.market_history_cache_ttl_seconds,
        ),
    )
    fund_client = httpx.AsyncClient(
        timeout=settings.fund_request_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "FinanceAssistant/1.0 (personal fund center)"},
    )
    tushare_fund_provider = TushareFundProvider(
        fund_client,
        token=settings.tushare_token,
        base_url=settings.tushare_base_url,
    )
    eastmoney_fund_provider = EastmoneyExperimentalFundProvider(
        fund_client,
        enabled=settings.enable_experimental_eastmoney_fund_data,
        trend_base_url=settings.eastmoney_fund_trend_base_url,
        mobile_base_url=settings.eastmoney_fund_mobile_base_url,
    )
    app.state.fund_provider = FallbackFundProvider(
        tushare_fund_provider,
        eastmoney_fund_provider,
    )
    fund_valuation_client = httpx.AsyncClient(
        timeout=settings.fund_valuation_request_timeout_seconds,
        follow_redirects=True,
        headers={"User-Agent": "FinanceAssistant/1.0 (personal experimental fund valuation)"},
    )
    eastmoney_valuation_provider = EastmoneyFundValuationProvider(
        fund_valuation_client,
        enabled=settings.enable_experimental_fund_valuation,
        base_url=settings.fund_valuation_base_url,
        stale_after_seconds=settings.fund_valuation_stale_seconds,
    )
    sina_valuation_provider = SinaFundValuationProvider(
        fund_valuation_client,
        enabled=settings.enable_experimental_sina_fund_valuation,
        base_url=settings.sina_fund_valuation_base_url,
        stale_after_seconds=settings.fund_valuation_stale_seconds,
    )
    app.state.fund_valuation_provider = FallbackFundValuationProvider(
        eastmoney_valuation_provider,
        sina_valuation_provider,
    )
    app.state.fund_cache = FundCacheRepository(
        app.state.infrastructure.redis,
        catalog_ttl_seconds=settings.fund_catalog_cache_ttl_seconds,
        nav_ttl_seconds=settings.fund_nav_cache_ttl_seconds,
        holdings_ttl_seconds=settings.fund_holdings_cache_ttl_seconds,
        valuation_ttl_seconds=settings.fund_valuation_cache_ttl_seconds,
        nav_history_ttl_seconds=settings.fund_nav_history_cache_ttl_seconds,
    )
    app.state.fund_user_id = settings.fund_user_id
    app.state.assistant_cache = AssistantCache(
        app.state.infrastructure.redis,
        ttl_seconds=settings.ai_assistant_cache_ttl_seconds,
    )
    assistant_client: httpx.AsyncClient | None = None
    app.state.assistant_router = None
    if settings.enable_ai and all(
        (settings.ai_base_url, settings.ai_api_key, settings.ai_model)
    ):
        assistant_client = httpx.AsyncClient(timeout=60.0)
        providers = ProviderRegistry()
        providers.register(
            OpenAICompatibleAdapter(
                settings.ai_base_url or "",
                settings.ai_api_key or "",
                settings.ai_model or "",
                assistant_client,
                max_tokens=settings.ai_assistant_max_output_tokens,
            )
        )
        app.state.assistant_router = ProviderRouter(providers, "openai-compatible")
    yield
    if assistant_client is not None:
        await assistant_client.aclose()
    await fund_valuation_client.aclose()
    await fund_client.aclose()
    await market_client.aclose()
    await app.state.infrastructure.close()


app = FastAPI(title="AI Finance WeChat Assistant", version="0.1.0", lifespan=lifespan)
app.include_router(wechat_router)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    infrastructure: Infrastructure = app.state.infrastructure
    async with infrastructure.engine.connect() as connection:
        await connection.exec_driver_sql("SELECT 1")
    await infrastructure.redis.ping()
    return {"status": "ready"}
