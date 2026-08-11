import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx

from .contracts import RawNewsPayload


class Jin10NotConfiguredError(RuntimeError):
    pass


class Jin10Adapter:
    """Official Jin10 Open Platform market-flash adapter."""

    name = "jin10"

    def __init__(
        self,
        secret_key: str,
        base_url: str,
        category: int = 1,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not secret_key.strip():
            raise Jin10NotConfiguredError("金十数据源未配置")
        self.secret_key = secret_key
        self.endpoint = f"{base_url.rstrip('/')}/flash"
        self.category = category
        self.client = client or httpx.AsyncClient(timeout=15.0)

    @staticmethod
    def _action(item: dict[str, Any]) -> str:
        value = str(item.get("action") or item.get("operation") or "created").lower()
        return {
            "add": "created",
            "insert": "created",
            "new": "created",
            "create": "created",
            "created": "created",
            "update": "updated",
            "updated": "updated",
            "modify": "updated",
            "delete": "deleted",
            "deleted": "deleted",
            "remove": "deleted",
        }.get(value, "created")

    async def fetch(self, cursor: dict[str, Any] | None = None) -> list[RawNewsPayload]:
        params: dict[str, str | int] = {"category": self.category}
        last_id = str((cursor or {}).get("last_id") or "").strip()
        if last_id:
            params["last_id"] = last_id
        response = await self.client.get(
            self.endpoint,
            params=params,
            headers={"secret-key": self.secret_key},
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TypeError("金十开放平台返回格式无效")
        code = body.get("code")
        if code not in (None, 0, 200, "0", "200"):
            raise ValueError(f"金十开放平台请求失败，code={code}")
        data = body.get("data", [])
        items = data.get("items", []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise TypeError("金十开放平台 data 字段格式无效")

        received_at = datetime.now(UTC)
        safe_headers = {
            "content-type": response.headers.get("content-type", ""),
            "date": response.headers.get("date", ""),
            "x-request-id": response.headers.get("x-request-id", ""),
        }
        payloads: list[RawNewsPayload] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            source_id = item.get("id")
            if source_id is None:
                continue
            canonical = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            content_hash = hashlib.sha256(canonical).hexdigest()
            revision = str(
                item.get("updated_at")
                or item.get("update_time")
                or item.get("version")
                or content_hash
            )
            payloads.append(
                RawNewsPayload(
                    source=self.name,
                    source_item_id=str(source_id),
                    raw_json=item,
                    headers=safe_headers,
                    received_at=received_at,
                    content_hash=content_hash,
                    fetch_version="jin10-open-platform-v1",
                    source_revision=revision[:128],
                    source_action=self._action(item),
                )
            )
        return payloads
