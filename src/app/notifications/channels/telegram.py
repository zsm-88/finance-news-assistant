"""Telegram Bot push channel — free, no rate limits for personal use."""

from typing import Any

import httpx

from .base import ChannelResult, NotificationMessage


class TelegramChannel:
    """Send markdown notifications via Telegram Bot API."""

    name = "telegram"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.client = client or httpx.AsyncClient(timeout=20.0)

    async def send(self, message: NotificationMessage) -> ChannelResult:
        """Send a markdown message to the configured Telegram chat."""
        text = f"*{message.title}*\n\n{message.body}"
        payload: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": False,
        }
        response = await self.client.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json=payload,
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        if not body.get("ok"):
            raise RuntimeError(
                f"Telegram rejected message: {body.get('description', 'unknown error')}"
            )
        result = body.get("result", {})
        return ChannelResult(str(result.get("message_id")), body)