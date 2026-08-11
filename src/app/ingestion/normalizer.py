import hashlib
import re
from datetime import UTC, datetime
from html import unescape
from typing import Any
from zoneinfo import ZoneInfo

from .contracts import NormalizedNews, RawNewsPayload


class DefaultNormalizer:
    def normalize(self, raw: RawNewsPayload) -> NormalizedNews:
        item: dict[str, Any] = raw.raw_json
        nested_value = item.get("data")
        nested: dict[str, Any] = nested_value if isinstance(nested_value, dict) else {}
        raw_content = nested.get("content") or item.get("content") or item.get("body") or ""
        content = unescape(re.sub(r"<[^>]+>", "", str(raw_content))).strip()
        title = str(item.get("title") or content).strip()
        published = item.get("published_at") or item.get("time")
        if isinstance(published, str):
            try:
                published_at = datetime.fromisoformat(published)
            except ValueError:
                published_at = raw.received_at
        else:
            published_at = raw.received_at
        if published_at.tzinfo is None:
            timezone = ZoneInfo("Asia/Shanghai") if raw.source == "jin10" else UTC
            published_at = published_at.replace(tzinfo=timezone)
        published_at = published_at.astimezone(UTC)
        url = item.get("url") or nested.get("url")
        return NormalizedNews(raw.source, raw.source_item_id, title, content, url, published_at, hashlib.sha256(content.encode()).hexdigest())
