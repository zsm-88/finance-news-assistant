from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TypeVar
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import ScalarSelect

from .base import utc_now
from .models import (
    AIReviewQueue,
    AuditLog,
    Event,
    JobRun,
    EventTimeline,
    FundPosition,
    FundWatchlist,
    MarketImpact,
    NewsAnalysis,
    NewsItem,
    Notification,
    NotificationTimeline,
    PromptVersion,
    PushDelivery,
    RawNews,
    SourceCursor,
    SystemConfig,
    UserPreference,
)

ModelT = TypeVar("ModelT")


@dataclass(slots=True)
class NewsReadRecord:
    news: NewsItem
    event: Event
    analysis: NewsAnalysis | None


class Repository[ModelT]:
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, entity_id: UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity


class EventRepository(Repository[Event]):
    model = Event

    async def by_key(self, event_key: str) -> Event | None:
        return await self.session.scalar(select(Event).where(Event.event_key == event_key, Event.deleted_at.is_(None)))

    async def list_active(self, limit: int = 100) -> Sequence[Event]:
        result = await self.session.scalars(
            select(Event).where(Event.deleted_at.is_(None)).order_by(Event.occurred_at.desc()).limit(limit)
        )
        return result.all()

    async def latest(self, limit: int = 10) -> Sequence[Event]:
        result = await self.session.scalars(
            select(Event)
            .where(Event.deleted_at.is_(None))
            .order_by(Event.occurred_at.desc())
            .limit(limit)
        )
        return result.all()

    async def in_window(self, start: datetime, end: datetime, limit: int = 200) -> Sequence[Event]:
        result = await self.session.scalars(
            select(Event)
            .where(
                Event.occurred_at >= start,
                Event.occurred_at <= end,
                Event.deleted_at.is_(None),
            )
            .order_by(Event.occurred_at.desc())
            .limit(limit)
        )
        return result.all()


class NewsRepository(Repository[NewsItem]):
    model = NewsItem

    async def by_source_id(self, source: str, source_item_id: str) -> NewsItem | None:
        return await self.session.scalar(select(NewsItem).where(NewsItem.source == source, NewsItem.source_item_id == source_item_id, NewsItem.deleted_at.is_(None)))

    async def any_by_source_id(self, source: str, source_item_id: str) -> NewsItem | None:
        return await self.session.scalar(
            select(NewsItem).where(
                NewsItem.source == source,
                NewsItem.source_item_id == source_item_id,
            )
        )

    async def for_event(self, event_id: UUID) -> Sequence[NewsItem]:
        result = await self.session.scalars(
            select(NewsItem).where(NewsItem.event_id == event_id, NewsItem.deleted_at.is_(None))
        )
        return result.all()

    def _latest_analysis_id(self) -> ScalarSelect[UUID]:
        return (
            select(NewsAnalysis.id)
            .where(
                NewsAnalysis.event_id == NewsItem.event_id,
                NewsAnalysis.deleted_at.is_(None),
            )
            .order_by(NewsAnalysis.created_at.desc())
            .limit(1)
            .correlate(NewsItem)
            .scalar_subquery()
        )

    async def list_page(
        self,
        page: int,
        page_size: int,
        importance: int | None = None,
        category: str | None = None,
    ) -> tuple[Sequence[NewsReadRecord], int]:
        conditions: list[ColumnElement[bool]] = [
            NewsItem.deleted_at.is_(None),
            Event.deleted_at.is_(None),
        ]
        if importance is not None:
            conditions.append(Event.importance == importance)

        query = (
            select(NewsItem, Event, NewsAnalysis)
            .join(Event, Event.id == NewsItem.event_id)
            .outerjoin(NewsAnalysis, NewsAnalysis.id == self._latest_analysis_id())
            .where(*conditions)
        )
        if category is not None:
            query = query.where(
                func.coalesce(NewsAnalysis.category, Event.event_type) == category
            )

        source_priority = case(
            (NewsItem.source == "chinanews", 0),
            (NewsItem.source == "tmtpost", 1),
            (NewsItem.source == "eastmoney", 2),
            (NewsItem.source == "cls", 3),
            (NewsItem.source == "stcn", 4),
            (NewsItem.source == "wallstreetcn", 5),
            (NewsItem.source == "cnbc", 6),
            else_=7,
        )
        rows = await self.session.execute(
            query
            .order_by(
                source_priority,
                NewsItem.published_at.desc(),
                Event.importance.desc().nullslast(),
            )
        )
        representatives: list[NewsReadRecord] = []
        seen_events: set[UUID] = set()
        for row in rows.all():
            record = NewsReadRecord(*row)
            if record.event.id in seen_events:
                continue
            seen_events.add(record.event.id)
            representatives.append(record)
        total = len(representatives)
        offset = (page - 1) * page_size
        return representatives[offset : offset + page_size], total

    async def read_detail(self, news_id: UUID) -> NewsReadRecord | None:
        row = (
            await self.session.execute(
                select(NewsItem, Event, NewsAnalysis)
                .join(Event, Event.id == NewsItem.event_id)
                .outerjoin(NewsAnalysis, NewsAnalysis.id == self._latest_analysis_id())
                .where(
                    NewsItem.id == news_id,
                    NewsItem.deleted_at.is_(None),
                    Event.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        return NewsReadRecord(*row) if row else None


class AnalysisRepository(Repository[NewsAnalysis]):
    model = NewsAnalysis

    async def latest_for_event(self, event_id: UUID) -> NewsAnalysis | None:
        return await self.session.scalar(
            select(NewsAnalysis)
            .where(NewsAnalysis.event_id == event_id, NewsAnalysis.deleted_at.is_(None))
            .order_by(NewsAnalysis.created_at.desc())
            .limit(1)
        )

    async def impacts(self, analysis_id: UUID) -> Sequence[MarketImpact]:
        result = await self.session.scalars(
            select(MarketImpact)
            .where(MarketImpact.analysis_id == analysis_id, MarketImpact.deleted_at.is_(None))
            .order_by(MarketImpact.created_at.asc())
        )
        return result.all()


class EventTimelineRepository(Repository[EventTimeline]):
    model = EventTimeline

    async def for_event(self, event_id: UUID) -> Sequence[EventTimeline]:
        result = await self.session.scalars(
            select(EventTimeline)
            .where(EventTimeline.event_id == event_id, EventTimeline.deleted_at.is_(None))
            .order_by(EventTimeline.created_at.asc())
        )
        return result.all()


class RawNewsRepository(Repository[RawNews]):
    model = RawNews

    async def by_fetch(self, source: str, source_item_id: str, fetch_version: str) -> RawNews | None:
        return await self.session.scalar(select(RawNews).where(RawNews.source == source, RawNews.source_item_id == source_item_id, RawNews.fetch_version == fetch_version, RawNews.deleted_at.is_(None)))

    async def by_revision(
        self,
        source: str,
        source_item_id: str,
        fetch_version: str,
        source_revision: str,
    ) -> RawNews | None:
        return await self.session.scalar(
            select(RawNews).where(
                RawNews.source == source,
                RawNews.source_item_id == source_item_id,
                RawNews.fetch_version == fetch_version,
                RawNews.source_revision == source_revision,
                RawNews.deleted_at.is_(None),
            )
        )


class SourceCursorRepository(Repository[SourceCursor]):
    model = SourceCursor

    async def for_source(self, source: str) -> SourceCursor | None:
        return await self.session.scalar(select(SourceCursor).where(SourceCursor.source == source, SourceCursor.deleted_at.is_(None)))


class SystemConfigRepository(Repository[SystemConfig]):
    model = SystemConfig

    async def by_key(self, key: str) -> SystemConfig | None:
        return await self.session.scalar(select(SystemConfig).where(SystemConfig.config_key == key, SystemConfig.deleted_at.is_(None)))

    async def all(self) -> Sequence[SystemConfig]:
        result = await self.session.scalars(
            select(SystemConfig).where(SystemConfig.deleted_at.is_(None)).order_by(SystemConfig.config_key.asc())
        )
        return result.all()


class AuditLogRepository(Repository[AuditLog]):
    model = AuditLog

    async def list_recent(self, limit: int = 50) -> Sequence[AuditLog]:
        result = await self.session.scalars(
            select(AuditLog).where(AuditLog.deleted_at.is_(None)).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        return result.all()


class AIReviewQueueRepository(Repository[AIReviewQueue]):
    model = AIReviewQueue

    async def list_pending(self, limit: int = 50) -> Sequence[AIReviewQueue]:
        result = await self.session.scalars(
            select(AIReviewQueue).where(AIReviewQueue.status == "pending", AIReviewQueue.deleted_at.is_(None)).order_by(AIReviewQueue.created_at.desc()).limit(limit)
        )
        return result.all()

    async def count_pending(self) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(AIReviewQueue).where(AIReviewQueue.status == "pending", AIReviewQueue.deleted_at.is_(None))
        )
        return result or 0


class NotificationRepository(Repository[Notification]):
    model = Notification

    async def pending_for_event(self, event_id: UUID, channel: str, now: datetime, merge_window_minutes: int = 15) -> Notification | None:
        cutoff = now - timedelta(minutes=merge_window_minutes)
        return await self.session.scalar(
            select(Notification)
            .where(Notification.event_id == event_id, Notification.channel == channel, Notification.status.in_(("pending", "delayed")), Notification.created_at >= cutoff, Notification.deleted_at.is_(None))
            .order_by(Notification.created_at.desc())
            .limit(1)
        )


class NotificationTimelineRepository(Repository[NotificationTimeline]):
    model = NotificationTimeline


class PushDeliveryRepository(Repository[PushDelivery]):
    model = PushDelivery

    async def list_page(
        self,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
    ) -> tuple[Sequence[PushDelivery], int]:
        conditions: list[ColumnElement[bool]] = [PushDelivery.deleted_at.is_(None)]
        if status_filter:
            conditions.append(PushDelivery.status == status_filter)
        query = select(PushDelivery).where(*conditions).order_by(PushDelivery.created_at.desc())
        total_query = select(func.count()).select_from(PushDelivery).where(*conditions)
        total = await self.session.scalar(total_query) or 0
        offset = (page - 1) * page_size
        result = await self.session.scalars(query.offset(offset).limit(page_size))
        return result.all(), total

    async def for_notification(self, notification_id: UUID, destination: str) -> PushDelivery | None:
        return await self.session.scalar(select(PushDelivery).where(PushDelivery.notification_id == notification_id, PushDelivery.destination == destination, PushDelivery.deleted_at.is_(None)))


class UserPreferenceRepository(Repository[UserPreference]):
    model = UserPreference

    async def for_user(self, user_id: UUID) -> UserPreference | None:
        return await self.session.scalar(select(UserPreference).where(UserPreference.user_id == user_id, UserPreference.deleted_at.is_(None)))


class FundWatchlistRepository(Repository[FundWatchlist]):
    model = FundWatchlist

    async def for_user(self, user_id: UUID) -> Sequence[FundWatchlist]:
        result = await self.session.scalars(
            select(FundWatchlist)
            .where(FundWatchlist.user_id == user_id, FundWatchlist.deleted_at.is_(None))
            .order_by(FundWatchlist.created_at.desc())
        )
        return result.all()

    async def add_code(self, user_id: UUID, fund_code: str) -> FundWatchlist:
        item = await self.session.scalar(
            select(FundWatchlist).where(
                FundWatchlist.user_id == user_id,
                FundWatchlist.fund_code == fund_code,
            )
        )
        if item is None:
            item = FundWatchlist(user_id=user_id, fund_code=fund_code)
            self.session.add(item)
        else:
            item.deleted_at = None
            item.updated_at = utc_now()
        await self.session.commit()
        return item

    async def contains(self, user_id: UUID, fund_code: str) -> bool:
        item_id = await self.session.scalar(
            select(FundWatchlist.id).where(
                FundWatchlist.user_id == user_id,
                FundWatchlist.fund_code == fund_code,
                FundWatchlist.deleted_at.is_(None),
            )
        )
        return item_id is not None

    async def remove_code(self, user_id: UUID, fund_code: str) -> bool:
        item = await self.session.scalar(
            select(FundWatchlist).where(
                FundWatchlist.user_id == user_id,
                FundWatchlist.fund_code == fund_code,
                FundWatchlist.deleted_at.is_(None),
            )
        )
        if item is None:
            return False
        item.deleted_at = utc_now()
        await self.session.commit()
        return True


class FundPositionRepository(Repository[FundPosition]):
    model = FundPosition

    async def for_user(self, user_id: UUID) -> Sequence[FundPosition]:
        result = await self.session.scalars(
            select(FundPosition).where(
                FundPosition.user_id == user_id,
                FundPosition.deleted_at.is_(None),
            )
        )
        return result.all()

    async def for_user_code(self, user_id: UUID, fund_code: str) -> FundPosition | None:
        return await self.session.scalar(
            select(FundPosition).where(
                FundPosition.user_id == user_id,
                FundPosition.fund_code == fund_code,
                FundPosition.deleted_at.is_(None),
            )
        )

    async def save(
        self,
        user_id: UUID,
        fund_code: str,
        shares: Decimal,
        average_cost: Decimal,
    ) -> FundPosition:
        item = await self.session.scalar(
            select(FundPosition).where(
                FundPosition.user_id == user_id,
                FundPosition.fund_code == fund_code,
            )
        )
        if item is None:
            item = FundPosition(
                user_id=user_id,
                fund_code=fund_code,
                shares=shares,
                average_cost=average_cost,
            )
            self.session.add(item)
        else:
            item.shares = shares
            item.average_cost = average_cost
            item.deleted_at = None
            item.updated_at = utc_now()
        await self.session.commit()
        return item

    async def remove(self, user_id: UUID, fund_code: str) -> bool:
        item = await self.for_user_code(user_id, fund_code)
        if item is None:
            return False
        item.deleted_at = utc_now()
        await self.session.commit()
        return True


class PromptVersionRepository(Repository[PromptVersion]):
    model = PromptVersion

    async def enabled(self, prompt_name: str) -> PromptVersion | None:
        return await self.session.scalar(select(PromptVersion).where(PromptVersion.prompt_name == prompt_name, PromptVersion.enabled.is_(True), PromptVersion.deleted_at.is_(None)).order_by(PromptVersion.created_at.desc()).limit(1))

    async def by_name_version(self, prompt_name: str, version: str) -> PromptVersion | None:
        return await self.session.scalar(
            select(PromptVersion).where(
                PromptVersion.prompt_name == prompt_name,
                PromptVersion.version == version,
                PromptVersion.deleted_at.is_(None),
            )
        )

    async def enable_exclusively(self, prompt: PromptVersion) -> None:
        values = await self.session.scalars(
            select(PromptVersion).where(
                PromptVersion.prompt_name == prompt.prompt_name,
                PromptVersion.deleted_at.is_(None),
            )
        )
        for value in values.all():
            value.enabled = value.id == prompt.id


class JobRunRepository(Repository[JobRun]):
    model = JobRun

    async def list_recent(self, limit: int = 50) -> Sequence[JobRun]:
        result = await self.session.scalars(
            select(JobRun).where(JobRun.deleted_at.is_(None)).order_by(JobRun.created_at.desc()).limit(limit)
        )
        return result.all()

    async def count_failed(self) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(JobRun).where(
                JobRun.status == "failed",
                JobRun.deleted_at.is_(None),
            )
        )
        return result or 0

    async def count_by_type(self, job_type: str, status: str) -> int:
        result = await self.session.scalar(
            select(func.count()).select_from(JobRun).where(
                JobRun.job_type == job_type,
                JobRun.status == status,
                JobRun.deleted_at.is_(None),
            )
        )
        return result or 0
