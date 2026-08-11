import hashlib
from datetime import UTC, datetime
from typing import Any

import httpx

from .contracts import RawNewsPayload, SourceAdapter


class HttpFetcher:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client or httpx.AsyncClient(timeout=20.0)

    async def fetch_json(self, adapter: SourceAdapter, url: str, cursor: dict[str, Any] | None = None) -> list[RawNewsPayload]:
        response = await self.client.get(url, params=cursor or {})
        response.raise_for_status()
        raw = response.json()
        values = raw if isinstance(raw, list) else raw.get("data", raw.get("items", []))
        received_at = datetime.now(UTC)
        return [
            RawNewsPayload(
                source=adapter.name,
                source_item_id=str(item.get("id") or item.get("news_id")),
                raw_json=item,
                headers=dict(response.headers),
                received_at=received_at,
                content_hash=hashlib.sha256(response.content).hexdigest(),
                fetch_version="v1",
            )
            for item in values
        ]

