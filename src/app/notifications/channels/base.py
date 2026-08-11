from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class NotificationMessage:
    title: str
    body: str
    destination: str


@dataclass(slots=True)
class ChannelResult:
    message_id: str | None
    raw_response: dict[str, Any]


class PushChannel(Protocol):
    name: str

    async def send(self, message: NotificationMessage) -> ChannelResult: ...

