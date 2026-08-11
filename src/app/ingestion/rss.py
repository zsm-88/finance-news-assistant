import hashlib
import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urldefrag
from xml.etree import ElementTree

import httpx

from .contracts import RawNewsPayload


class RssSourceAdapter:
    def __init__(self, name: str, endpoint: str, client: httpx.AsyncClient | None = None, fetch_version: str = "v1") -> None:
        self.name = name
        self.endpoint = endpoint
        self.client = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (compatible; FinanceAssistant/1.0)"})
        self.fetch_version = fetch_version
        self.cursor_update: dict[str, Any] = {}

    @staticmethod
    def _source_id(raw: dict[str, str]) -> str:
        guid = raw.get("guid", "").strip()
        link = urldefrag(raw.get("link", "").strip()).url
        if guid:
            return guid
        if link:
            return link
        material = "\n".join((raw.get("title", ""), raw.get("pubDate", "")))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _entry_hash(raw: dict[str, str]) -> str:
        material = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    async def fetch(self, cursor: dict[str, Any] | None = None) -> list[RawNewsPayload]:
        cursor = cursor or {}
        headers: dict[str, str] = {}
        etag = str(cursor.get("etag") or "").strip()
        last_modified = str(cursor.get("last_modified") or "").strip()
        allow_conditional = cursor.get("feed_drained", True) is not False
        if etag and allow_conditional:
            headers["If-None-Match"] = etag
        if last_modified and allow_conditional:
            headers["If-Modified-Since"] = last_modified
        response = await self.client.get(self.endpoint, headers=headers)
        now = datetime.now(UTC)
        self.cursor_update = {
            "etag": response.headers.get("etag", etag),
            "last_modified": response.headers.get("last-modified", last_modified),
            "last_checked_at": now.isoformat(),
            "last_status_code": response.status_code,
        }
        if response.status_code == httpx.codes.NOT_MODIFIED:
            return []
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
        received_at = now
        last_id = str(cursor.get("last_id") or "")
        entries: list[tuple[str, dict[str, str]]] = []
        for item in root.findall(".//item"):
            raw = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in item}
            entries.append((self._source_id(raw), raw))

        if last_id:
            cursor_index = next(
                (index for index, (source_id, _) in enumerate(entries) if source_id == last_id),
                None,
            )
            if cursor_index is not None:
                cursor_entry_hash = self._entry_hash(entries[cursor_index][1])
                last_entry_hash = str(cursor.get("last_entry_hash") or "")
                include_cursor = bool(last_entry_hash and cursor_entry_hash != last_entry_hash)
                entries = entries[: cursor_index + int(include_cursor)]
        entries.reverse()

        values: list[RawNewsPayload] = []
        for source_id, raw in entries:
            published = raw.get("pubDate") or ""
            if published:
                try:
                    raw["published_at"] = parsedate_to_datetime(published).astimezone(UTC).isoformat()
                except (TypeError, ValueError):
                    raw["published_at"] = received_at.isoformat()
            raw["content"] = raw.get("description", raw.get("title", ""))
            raw["url"] = raw.get("link") or ""
            entry_hash = self._entry_hash(raw)
            values.append(
                RawNewsPayload(
                    source=self.name,
                    source_item_id=source_id,
                    raw_json=raw,
                    headers={"etag": response.headers.get("etag", ""), "last-modified": response.headers.get("last-modified", "")},
                    received_at=received_at,
                    content_hash=entry_hash,
                    fetch_version=self.fetch_version,
                    source_revision=entry_hash,
                )
            )
        return values
