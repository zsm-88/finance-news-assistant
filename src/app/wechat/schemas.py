from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NewsListItem(BaseModel):
    id: UUID
    title: str
    summary: str | None
    source: str
    published_at: datetime
    importance: int | None
    category: str
    created_at: datetime


class NewsPage(BaseModel):
    items: list[NewsListItem]
    page: int
    page_size: int
    total: int
    has_more: bool


class MarketImpactItem(BaseModel):
    asset: str
    direction: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class AnalysisItem(BaseModel):
    id: UUID
    summary: str
    category: str
    importance: int
    confidence: float
    provider: str
    model: str
    duration_ms: int | None
    created_at: datetime


class EventItem(BaseModel):
    id: UUID
    title: str
    event_type: str
    importance: int | None
    summary: str | None
    occurred_at: datetime
    status: str


class NewsDetail(BaseModel):
    id: UUID
    title: str
    content: str
    url: str | None
    source: str
    published_at: datetime
    summary: str | None
    importance: int | None
    category: str
    analysis: AnalysisItem | None
    market_impacts: list[MarketImpactItem]
    event: EventItem
    related_news: list[NewsListItem]


class DashboardResponse(BaseModel):
    top_news: list[NewsListItem]
    latest_events: list[EventItem]
    system_status: str
    generated_at: datetime

