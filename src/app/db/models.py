from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, ModelMixin

Json = dict[str, object]
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Event(ModelMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint("event_key", name="uq_events_event_key"),
        Index("ix_events_occurred_at", "occurred_at"),
        CheckConstraint("importance IS NULL OR importance BETWEEN 1 AND 5", name="ck_event_importance"),
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    importance: Mapped[int | None] = mapped_column(nullable=True)
    markets: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_override: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    news_items: Mapped[list["NewsItem"]] = relationship(back_populates="event")


class NewsItem(ModelMixin, Base):
    __tablename__ = "news_items"
    __table_args__ = (
        UniqueConstraint("source", "source_item_id", name="uq_news_source_item"),
        Index("ix_news_published_at", "published_at"),
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    raw_news_id: Mapped[UUID | None] = mapped_column(ForeignKey("raw_news.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    event: Mapped[Event] = relationship(back_populates="news_items")


class RawNews(ModelMixin, Base):
    __tablename__ = "raw_news"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "source_item_id",
            "fetch_version",
            "source_revision",
            name="uq_raw_news_fetch_revision",
        ),
        CheckConstraint(
            "source_action IN ('created', 'updated', 'deleted')",
            name="ck_raw_news_source_action",
        ),
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_item_id: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_json: Mapped[Json] = mapped_column(JsonType, nullable=False)
    headers: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetch_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(128), nullable=False, default="initial")
    source_action: Mapped[str] = mapped_column(String(16), nullable=False, default="created")


class PromptVersion(ModelMixin, Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("prompt_name", "version", name="uq_prompt_name_version"),)
    prompt_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)


class NewsAnalysis(ModelMixin, Base):
    __tablename__ = "news_analyses"
    __table_args__ = (
        CheckConstraint("importance BETWEEN 1 AND 5", name="ck_analysis_importance"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_analysis_confidence"),
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    news_id: Mapped[UUID] = mapped_column(ForeignKey("news_items.id"), nullable=False)
    prompt_version_id: Mapped[UUID] = mapped_column(ForeignKey("prompt_versions.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    markets: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    importance: Mapped[int] = mapped_column(nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    raw_response: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    prompt_text_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)


class MarketImpact(ModelMixin, Base):
    __tablename__ = "market_impacts"
    __table_args__ = (
        CheckConstraint("direction IN ('bullish', 'bearish', 'neutral')", name="ck_impact_direction"),
        CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_impact_confidence"),
    )
    analysis_id: Mapped[UUID] = mapped_column(ForeignKey("news_analyses.id"), nullable=False)
    asset: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class EventTimeline(ModelMixin, Base):
    __tablename__ = "event_timelines"
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    payload: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)


class Notification(ModelMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_notification_priority"),
        Index("ix_notifications_event_status", "event_id", "status"),
    )
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    merged_from: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)


class UserPreference(ModelMixin, Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_preference_user"),
        CheckConstraint("minimum_importance BETWEEN 1 AND 5", name="ck_preference_importance"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    markets: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    assets: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JsonType, default=list, nullable=False)
    minimum_importance: Mapped[int] = mapped_column(default=1, nullable=False)
    quiet_hours_start: Mapped[str] = mapped_column(String(5), nullable=False, default="22:30")
    quiet_hours_end: Mapped[str] = mapped_column(String(5), nullable=False, default="07:30")


class FundWatchlist(ModelMixin, Base):
    __tablename__ = "fund_watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "fund_code", name="uq_fund_watchlist_user_code"),
        Index("ix_fund_watchlists_user_created", "user_id", "created_at"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fund_code: Mapped[str] = mapped_column(String(16), nullable=False)


class FundPosition(ModelMixin, Base):
    __tablename__ = "fund_positions"
    __table_args__ = (
        UniqueConstraint("user_id", "fund_code", name="uq_fund_position_user_code"),
        CheckConstraint("shares > 0", name="ck_fund_position_shares_positive"),
        CheckConstraint("average_cost >= 0", name="ck_fund_position_average_cost_nonnegative"),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fund_code: Mapped[str] = mapped_column(String(16), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    average_cost: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)


class NotificationTimeline(ModelMixin, Base):
    __tablename__ = "notification_timelines"
    notification_id: Mapped[UUID] = mapped_column(ForeignKey("notifications.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)


class PushDelivery(ModelMixin, Base):
    __tablename__ = "push_deliveries"
    __table_args__ = (UniqueConstraint("notification_id", "channel", "destination", name="uq_push_idempotency"),)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    notification_id: Mapped[UUID] = mapped_column(ForeignKey("notifications.id"), nullable=False)
    analysis_id: Mapped[UUID | None] = mapped_column(ForeignKey("news_analyses.id"), nullable=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    response_data: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobRun(ModelMixin, Base):
    __tablename__ = "job_runs"
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt: Mapped[int] = mapped_column(default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AIUsage(ModelMixin, Base):
    __tablename__ = "ai_usages"
    analysis_id: Mapped[UUID | None] = mapped_column(ForeignKey("news_analyses.id"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False, default="news_analysis")
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    success: Mapped[bool] = mapped_column(nullable=False, default=True)
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    cost: Mapped[float] = mapped_column(default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(default=0, nullable=False)


class SourceCursor(ModelMixin, Base):
    __tablename__ = "source_cursors"
    __table_args__ = (UniqueConstraint("source", name="uq_source_cursor_source"),)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    last_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cursor_data: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)


class SystemConfig(ModelMixin, Base):
    __tablename__ = "system_configs"
    __table_args__ = (UniqueConstraint("config_key", name="uq_system_config_key"),)
    config_key: Mapped[str] = mapped_column(String(128), nullable=False)
    config_value: Mapped[Json] = mapped_column(JsonType, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")


class AuditLog(ModelMixin, Base):
    __tablename__ = "audit_logs"
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    before_data: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    after_data: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    metadata_json: Mapped[Json] = mapped_column("metadata", JsonType, default=dict, nullable=False)


class AIReviewQueue(ModelMixin, Base):
    __tablename__ = "ai_review_queue"
    analysis_id: Mapped[UUID | None] = mapped_column(ForeignKey("news_analyses.id"), nullable=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    raw_response: Mapped[Json] = mapped_column(JsonType, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
