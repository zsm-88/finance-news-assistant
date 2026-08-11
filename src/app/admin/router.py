"""Admin web UI router — Jinja2 templates, dark financial theme."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from pathlib import Path

from app.config import get_settings
from app.db.repositories import (
    AIReviewQueueRepository,
    AnalysisRepository,
    AuditLogRepository,
    EventRepository,
    JobRunRepository,
    NewsRepository,
    PushDeliveryRepository,
    SystemConfigRepository,
)
from app.db.session import Infrastructure

router = APIRouter(prefix="/admin", tags=["admin"])

_templates_dir = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))
templates.env.globals["now"] = datetime.now


async def get_session(request: Request) -> AsyncSession:
    infrastructure: Infrastructure = request.app.state.infrastructure
    async with infrastructure.session_factory() as session:
        yield session


@router.get("", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request, session: AsyncSession = Depends(get_session)):
    """Admin dashboard — system overview."""
    settings = get_settings()
    jobs = JobRunRepository(session)
    events_repo = EventRepository(session)
    reviews = AIReviewQueueRepository(session)

    recent_jobs = await jobs.list_recent(20)
    failed_jobs_count = await jobs.count_failed()
    pending_reviews = await reviews.count_pending()
    recent_events = await events_repo.latest(10)

    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_events = await events_repo.in_window(today_start, now, 100)

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "settings": settings,
            "recent_jobs": recent_jobs,
            "failed_jobs_count": failed_jobs_count,
            "pending_reviews": pending_reviews,
            "recent_events": recent_events,
            "today_events_count": len(today_events),
            "collect_interval": settings.collect_interval_seconds,
            "crawler_enabled": settings.enable_crawler,
            "ai_enabled": settings.enable_ai,
            "push_enabled": settings.enable_push,
        },
    )


@router.get("/news", response_class=HTMLResponse, include_in_schema=False)
async def news_list(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    importance: int | None = Query(None, ge=1, le=5),
    category: str | None = Query(None, min_length=1, max_length=64),
    source: str | None = Query(None, min_length=1, max_length=32),
    session: AsyncSession = Depends(get_session),
):
    """News list with filters."""
    news = NewsRepository(session)
    records, total = await news.list_page(page, page_size, importance, category)
    if source:
        records = [r for r in records if r.news.source == source]
        total = len(records)
    total_pages = max(1, (total + page_size - 1) // page_size)

    return templates.TemplateResponse(
        request,
        "news.html",
        {
            "records": records,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "importance": importance,
            "category": category,
            "source": source,
        },
    )


@router.get("/news/{news_id}", response_class=HTMLResponse, include_in_schema=False)
async def news_detail(
    request: Request,
    news_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """News detail with analysis and delivery records."""
    news = NewsRepository(session)
    analyses_repo = AnalysisRepository(session)
    events_repo = EventRepository(session)
    deliveries_repo = PushDeliveryRepository(session)

    record = await news.read_detail(news_id)
    if record is None:
        return HTMLResponse("News not found", status_code=404)

    event = record.event
    news_item = record.news
    analysis = record.analysis

    related = await news.for_event(event.id)

    # Get deliveries for this event
    all_deliveries, _ = await deliveries_repo.list_page(1, 100)
    event_deliveries = [d for d in all_deliveries if d.event_id == event.id]

    return templates.TemplateResponse(
        request,
        "news_detail.html",
        {
            "news": news_item,
            "event": event,
            "analysis": analysis,
            "related_news": [r for r in related if r.id != news_id],
            "deliveries": event_deliveries,
        },
    )


@router.post("/news/{news_id}/reanalyze", include_in_schema=False)
async def reanalyze_news(
    request: Request,
    news_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Trigger re-analysis by resetting event status."""
    news = NewsRepository(session)
    events_repo = EventRepository(session)

    record = await news.read_detail(news_id)
    if record is None:
        return HTMLResponse("News not found", status_code=404)

    event = record.event
    event.status = "pending"
    await session.commit()

    return RedirectResponse(url=f"/admin/news/{news_id}", status_code=302)


@router.get("/deliveries", response_class=HTMLResponse, include_in_schema=False)
async def delivery_list(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None, alias="status", min_length=1, max_length=32),
    session: AsyncSession = Depends(get_session),
):
    """Delivery log with status filter."""
    deliveries_repo = PushDeliveryRepository(session)
    items, total = await deliveries_repo.list_page(page, page_size, status_filter)
    total_pages = max(1, (total + page_size - 1) // page_size)

    return templates.TemplateResponse(
        request,
        "deliveries.html",
        {
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "status_filter": status_filter,
        },
    )


@router.post("/deliveries/{delivery_id}/retry", include_in_schema=False)
async def retry_delivery(
    request: Request,
    delivery_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Retry a failed/dead-letter delivery."""
    deliveries_repo = PushDeliveryRepository(session)
    delivery = await deliveries_repo.get(delivery_id)
    if delivery is None:
        return HTMLResponse("Delivery not found", status_code=404)

    delivery.status = "pending"
    delivery.attempts = 0
    delivery.last_error = None
    await session.commit()

    return RedirectResponse(url="/admin/deliveries", status_code=302)


@router.get("/events", response_class=HTMLResponse, include_in_schema=False)
async def event_list(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """Events list."""
    events_repo = EventRepository(session)
    events = await events_repo.list_active(limit)

    return templates.TemplateResponse(
        request,
        "events.html",
        {
            "events": events,
        },
    )


@router.get("/analysis-queue", response_class=HTMLResponse, include_in_schema=False)
async def analysis_queue(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
):
    """AI review queue — analyses pending review."""
    reviews_repo = AIReviewQueueRepository(session)
    items = await reviews_repo.list_pending(limit)
    count = await reviews_repo.count_pending()

    return templates.TemplateResponse(
        request,
        "analysis.html",
        {
            "items": items,
            "count": count,
        },
    )


@router.get("/config", response_class=HTMLResponse, include_in_schema=False)
async def config_view(
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """Runtime configuration viewer."""
    settings = get_settings()
    configs_repo = SystemConfigRepository(session)
    system_configs = await configs_repo.all()

    audit_repo = AuditLogRepository(session)
    recent_audits = await audit_repo.list_recent(20)

    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "settings": settings,
            "system_configs": system_configs,
            "recent_audits": recent_audits,
        },
    )