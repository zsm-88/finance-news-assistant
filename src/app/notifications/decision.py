from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum
from typing import cast
from zoneinfo import ZoneInfo

from app.db.models import Event, Notification, UserPreference


class DecisionAction(StrEnum):
    PUSH = "push"
    DELAY = "delay"
    MERGE = "merge"
    IGNORE = "ignore"


@dataclass(slots=True)
class NotificationDecision:
    action: DecisionAction
    scheduled_at: datetime
    reason: str


class DecisionEngine:
    def __init__(self, timezone_name: str = "Asia/Shanghai") -> None:
        self.timezone = ZoneInfo(timezone_name)

    def decide(self, event: Event, preference: UserPreference, now: datetime, existing: Notification | None = None) -> NotificationDecision:
        local_now = now.astimezone(self.timezone)
        if event.importance is None or event.importance < preference.minimum_importance:
            return NotificationDecision(DecisionAction.IGNORE, now, "below minimum importance")
        if preference.categories and event.event_type not in preference.categories:
            return NotificationDecision(DecisionAction.IGNORE, now, "category is not subscribed")
        market_data = event.markets or {}
        raw_markets = market_data.get("markets", [])
        raw_assets = market_data.get("assets", [])
        event_markets = set(cast(list[str], raw_markets)) if isinstance(raw_markets, list) else set()
        event_assets = set(cast(list[str], raw_assets)) if isinstance(raw_assets, list) else set()
        if preference.markets and event_markets and not event_markets.intersection(preference.markets):
            return NotificationDecision(DecisionAction.IGNORE, now, "market is not subscribed")
        if preference.assets and event_assets and not event_assets.intersection(preference.assets):
            return NotificationDecision(DecisionAction.IGNORE, now, "asset is not subscribed")
        if existing is not None:
            return NotificationDecision(DecisionAction.MERGE, existing.scheduled_at, "pending notification exists")
        start = time.fromisoformat(preference.quiet_hours_start)
        end = time.fromisoformat(preference.quiet_hours_end)
        current = local_now.time().replace(tzinfo=None)
        in_quiet = current >= start or current < end if start > end else start <= current < end
        if in_quiet and event.importance < 5:
            end_date = local_now.date() + (timedelta(days=1) if current >= start > end else timedelta())
            scheduled = datetime.combine(end_date, end, self.timezone)
            return NotificationDecision(DecisionAction.DELAY, scheduled, "quiet hours")
        return NotificationDecision(DecisionAction.PUSH, now, "eligible for immediate delivery")
