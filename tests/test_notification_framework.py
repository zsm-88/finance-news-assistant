from datetime import UTC, datetime
from uuid import uuid4

from app.db.models import Event, Notification, UserPreference
from app.notifications.decision import DecisionAction, DecisionEngine
from app.notifications.merge import MergeEngine


def preference(minimum: int = 1) -> UserPreference:
    return UserPreference(user_id=uuid4(), markets=[], assets=[], categories=[], minimum_importance=minimum, quiet_hours_start="22:30", quiet_hours_end="07:30")


def event(importance: int) -> Event:
    return Event(id=uuid4(), event_key=str(uuid4()), title="CPI", event_type="macro", occurred_at=datetime.now(UTC), status="succeeded", importance=importance)


def test_quiet_hours_delays_non_critical_event() -> None:
    now = datetime(2026, 8, 8, 15, 0, tzinfo=UTC)  # 23:00 Asia/Shanghai
    decision = DecisionEngine().decide(event(4), preference(), now)
    assert decision.action == DecisionAction.DELAY


def test_five_star_event_bypasses_quiet_hours() -> None:
    now = datetime(2026, 8, 8, 15, 0, tzinfo=UTC)
    decision = DecisionEngine().decide(event(5), preference(), now)
    assert decision.action == DecisionAction.PUSH


def test_preference_minimum_importance_ignores_event() -> None:
    decision = DecisionEngine().decide(event(2), preference(3), datetime.now(UTC))
    assert decision.action == DecisionAction.IGNORE


def test_merge_engine_preserves_highest_priority() -> None:
    now = datetime.now(UTC)
    target = Notification(id=uuid4(), event_id=uuid4(), user_id=uuid4(), priority=3, channel="wecom", scheduled_at=now, status="pending")
    incoming = Notification(id=uuid4(), event_id=target.event_id, user_id=target.user_id, priority=5, channel="wecom", scheduled_at=now, status="pending")
    MergeEngine().merge(target, incoming)
    assert target.priority == 5
    assert str(incoming.id) in target.merged_from
    assert incoming.status == "merged"

