from dataclasses import dataclass
from typing import Any

from app.db.models import Event, NewsAnalysis, NewsItem


@dataclass(slots=True)
class AnalysisContext:
    event: Event
    news: NewsItem
    related_news: list[NewsItem]
    history: list[NewsAnalysis]

    def as_dict(self) -> dict[str, Any]:
        def item(value: NewsItem) -> dict[str, Any]:
            return {"title": value.title, "content": value.content, "source": value.source, "published_at": value.published_at.isoformat()}

        return {
            "event": {"title": self.event.title, "event_type": self.event.event_type, "occurred_at": self.event.occurred_at.isoformat()},
            "news": item(self.news),
            "related_news": [item(value) for value in self.related_news],
            "history": [{"summary": value.summary, "importance": value.importance, "created_at": value.created_at.isoformat()} for value in self.history],
        }


class ContextBuilder:
    async def build(self, event: Event, news: NewsItem, related_news: list[NewsItem] | None = None, history: list[NewsAnalysis] | None = None) -> AnalysisContext:
        return AnalysisContext(event, news, related_news or [], history or [])

