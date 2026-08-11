from typing import Any

import httpx

from .base import ChannelResult, NotificationMessage


class WeComChannel:
    name = "wecom"

    def __init__(self, webhook_url: str, client: httpx.AsyncClient | None = None) -> None:
        self.webhook_url = webhook_url
        self.client = client or httpx.AsyncClient(timeout=20.0)

    async def send(self, message: NotificationMessage) -> ChannelResult:
        response = await self.client.post(self.webhook_url, json={"msgtype": "markdown", "markdown": {"content": f"## {message.title}\n{message.body}"}})
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        if int(body.get("errcode", 0)) != 0:
            raise RuntimeError(f"WeCom rejected notification: {body.get('errmsg', 'unknown error')}")
        return ChannelResult(str(body.get("msgid")) if body.get("msgid") else None, body)

