from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event, Notification, NotificationTimeline, PushDelivery, UserPreference
from app.db.repositories import (
    NotificationRepository,
    NotificationTimelineRepository,
    PushDeliveryRepository,
)

from .channels.base import NotificationMessage
from .channels.registry import PushChannelRegistry
from .decision import DecisionAction, DecisionEngine
from .merge import MergeEngine


class NotificationService:
    def __init__(self, session: AsyncSession, channels: PushChannelRegistry, decision_engine: DecisionEngine | None = None) -> None:
        self.session = session
        self.channels = channels
        self.decisions = decision_engine or DecisionEngine()
        self.merger = MergeEngine()
        self.notifications = NotificationRepository(session)
        self.timelines = NotificationTimelineRepository(session)
        self.deliveries = PushDeliveryRepository(session)

    async def process(self, event: Event, preference: UserPreference, channel: str, destination: str, now: datetime | None = None) -> Notification:
        current = now or datetime.now(UTC)
        existing = await self.notifications.pending_for_event(event.id, channel, current)
        decision = self.decisions.decide(event, preference, current, existing)
        notification = Notification(event_id=event.id, user_id=preference.user_id, priority=event.importance or 1, channel=channel, scheduled_at=decision.scheduled_at, status="pending", merged_from=[])
        await self.notifications.add(notification)
        await self._timeline(notification.id, "created", {"decision": decision.action.value, "reason": decision.reason})

        if decision.action == DecisionAction.IGNORE:
            notification.status = "ignored"
            await self._timeline(notification.id, "cancelled", {"reason": decision.reason})
        elif decision.action == DecisionAction.DELAY:
            notification.status = "delayed"
            await self._timeline(notification.id, "delayed", {"scheduled_at": decision.scheduled_at.isoformat()})
        elif decision.action == DecisionAction.MERGE and existing is not None:
            self.merger.merge(existing, notification)
            await self._timeline(existing.id, "merged", {"merged_notification_id": str(notification.id)})
            await self._timeline(notification.id, "merged", {"target_notification_id": str(existing.id)})
            await self.session.commit()
            return existing
        else:
            await self._deliver(event, notification, destination)

        await self.session.commit()
        return notification

    async def _deliver(self, event: Event, notification: Notification, destination: str) -> None:
        delivery = await self.deliveries.for_notification(notification.id, destination)
        if delivery is None:
            delivery = PushDelivery(event_id=event.id, notification_id=notification.id, analysis_id=None, channel=notification.channel, destination=destination, status="pending", attempts=0)
            await self.deliveries.add(delivery)
        else:
            delivery.status = "pending"
        try:
            result = await self.channels.get(notification.channel).send(NotificationMessage(event.title, event.summary or event.title, destination))
        except Exception as exc:  # noqa: BLE001
            delivery.status = "failed"
            delivery.attempts += 1
            delivery.last_error = str(exc)
            notification.status = "failed"
            notification.retry_count += 1
            await self._timeline(notification.id, "failed", {"error": str(exc)})
            return
        delivery.status = "sent"
        delivery.attempts += 1
        delivery.provider_message_id = result.message_id
        delivery.response_data = result.raw_response
        delivery.sent_at = datetime.now(UTC)
        notification.status = "sent"
        await self._timeline(notification.id, "pushed", {"delivery_id": str(delivery.id)})

    async def retry(self, event: Event, notification: Notification, destination: str) -> Notification:
        notification.status = "pending"
        notification.retry_count += 1
        await self._timeline(notification.id, "retried", {"retry_count": notification.retry_count})
        await self._deliver(event, notification, destination)
        await self.session.commit()
        return notification

    async def _timeline(self, notification_id: UUID, action: str, payload: dict[str, object]) -> None:
        await self.timelines.add(NotificationTimeline(notification_id=notification_id, action=action, payload=payload))
