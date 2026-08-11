from dataclasses import asdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utc_now
from app.db.models import Event, EventTimeline, NewsItem, RawNews, SourceCursor
from app.db.repositories import (
    EventRepository,
    EventTimelineRepository,
    NewsRepository,
    RawNewsRepository,
    SourceCursorRepository,
)

from .contracts import EventMatcher, NewsNormalizer, SourceAdapter


class IngestionService:
    def __init__(self, session: AsyncSession, adapter: SourceAdapter, normalizer: NewsNormalizer, matcher: EventMatcher) -> None:
        self.raw_news = RawNewsRepository(session)
        self.events = EventRepository(session)
        self.news = NewsRepository(session)
        self.cursors = SourceCursorRepository(session)
        self.timelines = EventTimelineRepository(session)
        self.adapter = adapter
        self.normalizer = normalizer
        self.matcher = matcher

    async def ingest(self, limit: int = 10) -> list[NewsItem]:
        cursor_record = await self.cursors.for_source(self.adapter.name)
        cursor = None if cursor_record is None else {"last_id": cursor_record.last_id, "last_time": cursor_record.last_time, **(cursor_record.cursor_data or {})}
        payloads = await self.adapter.fetch(cursor)
        inserted: list[NewsItem] = []
        last_processed = None
        processed_count = 0
        for payload in payloads:
            last_processed = payload
            processed_count += 1
            existing_raw = await self.raw_news.by_revision(
                payload.source,
                payload.source_item_id,
                payload.fetch_version,
                payload.source_revision,
            )
            if existing_raw is not None:
                continue
            raw_record = await self.raw_news.add(RawNews(**asdict(payload)))
            existing_news = await self.news.any_by_source_id(payload.source, payload.source_item_id)
            if payload.source_action == "deleted":
                if existing_news is not None:
                    existing_news.deleted_at = utc_now()
                    await self.timelines.add(
                        EventTimeline(
                            event_id=existing_news.event_id,
                            event_type="news_deleted",
                            entity_type="news_item",
                            entity_id=existing_news.id,
                            payload={"source": payload.source, "revision": payload.source_revision},
                        )
                    )
                continue
            normalized = self.normalizer.normalize(payload)
            event_key = await self.matcher.match(normalized)
            event = await self.events.by_key(event_key)
            if event is None:
                event = Event(event_key=event_key, title=normalized.title, event_type="unknown", occurred_at=normalized.published_at, status="pending")
                await self.events.add(event)
            if existing_news is not None:
                existing_news.raw_news_id = raw_record.id
                existing_news.event_id = event.id
                existing_news.title = normalized.title
                existing_news.content = normalized.content
                existing_news.url = normalized.url
                existing_news.published_at = normalized.published_at
                existing_news.collected_at = payload.received_at
                existing_news.content_hash = normalized.content_hash
                existing_news.deleted_at = None
                await self.timelines.add(
                    EventTimeline(
                        event_id=event.id,
                        event_type="news_updated",
                        entity_type="news_item",
                        entity_id=existing_news.id,
                        payload={"source": payload.source, "revision": payload.source_revision},
                    )
                )
                inserted.append(existing_news)
            else:
                news = NewsItem(raw_news_id=raw_record.id, event_id=event.id, source=normalized.source, source_item_id=normalized.source_item_id, title=normalized.title, content=normalized.content, url=normalized.url, published_at=normalized.published_at, collected_at=payload.received_at, content_hash=normalized.content_hash)
                await self.news.add(news)
                await self.timelines.add(
                    EventTimeline(
                        event_id=event.id,
                        event_type="news_collected",
                        entity_type="news_item",
                        entity_id=news.id,
                        payload={"source": payload.source, "revision": payload.source_revision},
                    )
                )
                inserted.append(news)
            if len(inserted) >= limit:
                break

        cursor_update = getattr(self.adapter, "cursor_update", {})
        if last_processed is not None or cursor_update:
            if cursor_record is None:
                cursor_record = SourceCursor(source=self.adapter.name, cursor_data={})
                await self.cursors.add(cursor_record)
            if last_processed is not None:
                cursor_record.last_id = last_processed.source_item_id
                cursor_record.last_time = last_processed.received_at
            cursor_record.cursor_data = {
                **(cursor_record.cursor_data or {}),
                **cursor_update,
                **(
                    {"last_entry_hash": last_processed.content_hash}
                    if last_processed is not None
                    else {}
                ),
                **(
                    {"feed_drained": processed_count == len(payloads)}
                    if cursor_update and payloads
                    else {}
                ),
            }
        return inserted
