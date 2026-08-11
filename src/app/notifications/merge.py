from app.db.models import Notification


class MergeEngine:
    def merge(self, target: Notification, incoming: Notification) -> Notification:
        merged = list(dict.fromkeys([*(target.merged_from or []), str(incoming.id)]))
        target.merged_from = merged
        target.priority = max(target.priority, incoming.priority)
        target.scheduled_at = min(target.scheduled_at, incoming.scheduled_at)
        incoming.status = "merged"
        return target
