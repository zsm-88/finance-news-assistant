from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.context import AssistantContextBuilder
from app.assistant.contracts import AssistantChatRequest, AssistantChatResponse
from app.assistant.repository import AssistantUsageRepository
from app.assistant.service import (
    AssistantProviderError,
    AssistantUnavailableError,
    FinanceAssistantService,
)
from app.config import Settings, get_settings
from app.db.repositories import (
    AnalysisRepository,
    EventRepository,
    FundPositionRepository,
    FundWatchlistRepository,
    NewsRepository,
)
from app.db.session import Infrastructure
from app.fund.contracts import (
    FundDetailView,
    FundHistoryRange,
    FundMutationResponse,
    FundNavHistoryResponse,
    FundPositionInput,
    FundSearchResponse,
    FundWatchlistResponse,
)
from app.fund.service import FundService
from app.market.contracts import (
    HistoryPeriod,
    HistoryRange,
    MarketHistoryResponse,
    MarketListResponse,
    MarketQuote,
)
from app.market.service import MarketHistoryService, MarketService

from .schemas import DashboardResponse, EventItem, NewsDetail, NewsPage
from .service import WeChatReadService

router = APIRouter(prefix="/api/v1/wechat", tags=["wechat"])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    infrastructure: Infrastructure = request.app.state.infrastructure
    async with infrastructure.session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_service(
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> WeChatReadService:
    return WeChatReadService(
        NewsRepository(session),
        EventRepository(session),
        AnalysisRepository(session),
        chinese_source_configured=settings.enable_chinanews or settings.enable_tmtpost,
    )


ServiceDep = Annotated[WeChatReadService, Depends(get_service)]


def get_market_service(request: Request) -> MarketService:
    return request.app.state.market_service


MarketServiceDep = Annotated[MarketService, Depends(get_market_service)]


def get_market_history_service(request: Request) -> MarketHistoryService:
    return request.app.state.market_history_service


MarketHistoryServiceDep = Annotated[MarketHistoryService, Depends(get_market_history_service)]


def get_fund_service(request: Request, session: SessionDep) -> FundService:
    return FundService(
        request.app.state.fund_provider,
        request.app.state.fund_valuation_provider,
        request.app.state.fund_cache,
        FundWatchlistRepository(session),
        FundPositionRepository(session),
        UUID(request.app.state.fund_user_id),
    )


FundServiceDep = Annotated[FundService, Depends(get_fund_service)]


def get_assistant_service(
    request: Request,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> FinanceAssistantService:
    funds = get_fund_service(request, session)
    context_builder = AssistantContextBuilder(
        EventRepository(session),
        NewsRepository(session),
        AnalysisRepository(session),
        request.app.state.market_service,
        funds,
        max_events=settings.ai_assistant_max_events,
    )
    return FinanceAssistantService(
        getattr(request.app.state, "assistant_router", None),
        context_builder,
        AssistantUsageRepository(session),
        request.app.state.assistant_cache,
    )


AssistantServiceDep = Annotated[FinanceAssistantService, Depends(get_assistant_service)]


@router.post("/ai/chat", response_model=AssistantChatResponse)
async def ai_chat(
    value: AssistantChatRequest,
    service: AssistantServiceDep,
) -> AssistantChatResponse:
    try:
        return await service.chat(value)
    except AssistantUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AssistantProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.get("/news", response_model=NewsPage)
async def list_news(
    service: ServiceDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    importance: int | None = Query(None, ge=1, le=5),
    category: str | None = Query(None, min_length=1, max_length=64),
) -> NewsPage:
    return await service.list_news(page, page_size, importance, category)


@router.get("/news/{news_id}", response_model=NewsDetail)
async def news_detail(
    news_id: UUID,
    service: ServiceDep,
) -> NewsDetail:
    result = await service.news_detail(news_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="News not found")
    return result


@router.get("/events", response_model=list[EventItem])
async def list_events(
    service: ServiceDep,
    limit: int = Query(20, ge=1, le=100),
) -> list[EventItem]:
    return await service.list_events(limit)


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(service: ServiceDep) -> DashboardResponse:
    return await service.dashboard()


@router.get("/market", response_model=MarketListResponse)
async def market(service: MarketServiceDep) -> MarketListResponse:
    return await service.list_quotes()


@router.get("/market/{symbol}", response_model=MarketQuote)
async def market_detail(
    service: MarketServiceDep,
    symbol: str = Path(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$"),
) -> MarketQuote:
    result = await service.quote(symbol)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market symbol not found")
    return result


@router.get("/market/{symbol}/history", response_model=MarketHistoryResponse)
async def market_history(
    service: MarketHistoryServiceDep,
    symbol: str = Path(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$"),
    period: Annotated[HistoryPeriod, Query()] = "day",
    history_range: Annotated[HistoryRange, Query(alias="range")] = "1m",
) -> MarketHistoryResponse:
    result = await service.history(symbol, period, history_range)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Market symbol not found")
    return result


@router.get("/funds/search", response_model=FundSearchResponse)
async def search_funds(
    service: FundServiceDep,
    q: str = Query(min_length=1, max_length=64),
    limit: int = Query(20, ge=1, le=50),
    refresh: bool = Query(False),
) -> FundSearchResponse:
    return await service.search(q, limit, refresh)


@router.get("/funds/watchlist", response_model=FundWatchlistResponse)
async def fund_watchlist(
    service: FundServiceDep,
    refresh: bool = Query(False),
) -> FundWatchlistResponse:
    return await service.watchlist(refresh)


@router.post(
    "/funds/watchlist/{fund_code}",
    response_model=FundMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_fund_watchlist(
    service: FundServiceDep,
    fund_code: str = Path(pattern=r"^[0-9]{6}\.(OF|SH|SZ)$"),
) -> FundMutationResponse:
    return await service.add_watchlist(fund_code)


@router.delete("/funds/watchlist/{fund_code}", response_model=FundMutationResponse)
async def delete_fund_watchlist(
    service: FundServiceDep,
    fund_code: str = Path(pattern=r"^[0-9]{6}\.(OF|SH|SZ)$"),
) -> FundMutationResponse:
    return await service.remove_watchlist(fund_code)


@router.put("/funds/positions/{fund_code}", response_model=FundMutationResponse)
async def save_fund_position(
    value: FundPositionInput,
    service: FundServiceDep,
    fund_code: str = Path(pattern=r"^[0-9]{6}\.(OF|SH|SZ)$"),
) -> FundMutationResponse:
    return await service.save_position(fund_code, value)


@router.delete("/funds/positions/{fund_code}", response_model=FundMutationResponse)
async def delete_fund_position(
    service: FundServiceDep,
    fund_code: str = Path(pattern=r"^[0-9]{6}\.(OF|SH|SZ)$"),
) -> FundMutationResponse:
    return await service.remove_position(fund_code)


@router.get("/funds/{fund_code}/nav-history", response_model=FundNavHistoryResponse)
async def fund_nav_history(
    service: FundServiceDep,
    fund_code: str = Path(pattern=r"^[0-9]{6}\.(OF|SH|SZ)$"),
    history_range: Annotated[FundHistoryRange, Query(alias="range")] = "3m",
    refresh: bool = Query(False),
) -> FundNavHistoryResponse:
    return await service.nav_history(fund_code, history_range, refresh)


@router.get("/funds/{fund_code}", response_model=FundDetailView)
async def fund_detail(
    service: FundServiceDep,
    fund_code: str = Path(pattern=r"^[0-9]{6}\.(OF|SH|SZ)$"),
    refresh: bool = Query(False),
) -> FundDetailView:
    result = await service.detail(fund_code, refresh)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fund not found")
    return result
