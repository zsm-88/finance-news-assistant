from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class RawNewsPayload:
    source: str
    source_item_id: str
    raw_json: dict[str, Any]
    headers: dict[str, str]
    received_at: datetime
    content_hash: str
    fetch_version: str
    source_revision: str = "initial"
    source_action: str = "created"


@dataclass(slots=True)
class NormalizedNews:
    source: str
    source_item_id: str
    title: str
    content: str
    url: str | None
    published_at: datetime
    content_hash: str


class SourceAdapter(Protocol):
    name: str

    async def fetch(self, cursor: dict[str, Any] | None = None) -> list[RawNewsPayload]: ...


class NewsNormalizer(Protocol):
    def normalize(self, raw: RawNewsPayload) -> NormalizedNews: ...


class EventMatcher(Protocol):
    async def match(self, news: NormalizedNews) -> str: ...
