from datetime import UTC, datetime
from uuid import UUID

from app.db.models import Event, NewsAnalysis
from app.db.repositories import AnalysisRepository, EventRepository, NewsReadRecord, NewsRepository

from .schemas import (
    AnalysisItem,
    DashboardResponse,
    EventItem,
    MarketImpactItem,
    NewsDetail,
    NewsListItem,
    NewsPage,
)


class WeChatReadService:
    def __init__(
        self,
        news: NewsRepository,
        events: EventRepository,
        analyses: AnalysisRepository,
        chinese_source_configured: bool = True,
    ) -> None:
        self.news = news
        self.events = events
        self.analyses = analyses
        self.chinese_source_configured = chinese_source_configured

    @staticmethod
    def _source_name(source: str) -> str:
        return {
            "chinanews": "中新网财经",
            "tmtpost": "钛媒体",
            "jin10": "金十数据",
            "cnbc": "CNBC",
            "cls": "财联社",
            "stcn": "证券时报",
            "eastmoney": "东方财富",
        }.get(source.lower(), source.upper())

    def _news_item(self, record: NewsReadRecord) -> NewsListItem:
        return NewsListItem(
            id=record.news.id,
            title=record.news.title,
            summary=record.analysis.summary if record.analysis else record.event.summary,
            source=self._source_name(record.news.source),
            published_at=record.news.published_at,
            importance=record.event.importance,
            category=record.analysis.category if record.analysis else record.event.event_type,
            created_at=record.news.created_at,
        )

    def _event_item(self, event: Event) -> EventItem:
        return EventItem(
            id=event.id,
            title=event.title,
            event_type=event.event_type,
            importance=event.importance,
            summary=event.summary,
            occurred_at=event.occurred_at,
            status=event.status,
        )

    def _analysis_item(self, analysis: NewsAnalysis) -> AnalysisItem:
        return AnalysisItem(
            id=analysis.id,
            summary=analysis.summary,
            category=analysis.category,
            importance=analysis.importance,
            confidence=analysis.confidence,
            provider=analysis.provider,
            model=analysis.model,
            duration_ms=analysis.duration_ms,
            created_at=analysis.created_at,
        )

    async def list_news(
        self,
        page: int,
        page_size: int,
        importance: int | None,
        category: str | None,
    ) -> NewsPage:
        records, total = await self.news.list_page(page, page_size, importance, category)
        return NewsPage(
            items=[self._news_item(record) for record in records],
            page=page,
            page_size=page_size,
            total=total,
            has_more=page * page_size < total,
        )

    async def news_detail(self, news_id: UUID) -> NewsDetail | None:
        record = await self.news.read_detail(news_id)
        if record is None:
            return None
        related = await self.news.for_event(record.event.id)
        impacts = await self.analyses.impacts(record.analysis.id) if record.analysis else []
        return NewsDetail(
            id=record.news.id,
            title=record.news.title,
            content=record.news.content,
            url=record.news.url,
            source=self._source_name(record.news.source),
            published_at=record.news.published_at,
            summary=record.analysis.summary if record.analysis else record.event.summary,
            importance=record.event.importance,
            category=record.analysis.category if record.analysis else record.event.event_type,
            analysis=self._analysis_item(record.analysis) if record.analysis else None,
            market_impacts=[
                MarketImpactItem(
                    asset=impact.asset,
                    direction=impact.direction,
                    confidence=impact.confidence,
                    reason=impact.reason,
                )
                for impact in impacts
            ],
            event=self._event_item(record.event),
            related_news=[
                NewsListItem(
                    id=item.id,
                    title=item.title,
                    summary=record.event.summary,
                    source=self._source_name(item.source),
                    published_at=item.published_at,
                    importance=record.event.importance,
                    category=record.event.event_type,
                    created_at=item.created_at,
                )
                for item in related
                if item.id != record.news.id
            ],
        )

    async def list_events(self, limit: int = 20) -> list[EventItem]:
        return [self._event_item(event) for event in await self.events.latest(limit)]

    async def dashboard(self) -> DashboardResponse:
        records, _ = await self.news.list_page(1, 5)
        return DashboardResponse(
            top_news=[self._news_item(record) for record in records],
            latest_events=[self._event_item(record.event) for record in records],
            system_status="正常" if self.chinese_source_configured else "中文新闻源未配置",
            generated_at=datetime.now(UTC),
        )
