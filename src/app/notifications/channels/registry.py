from .base import PushChannel


class PushChannelRegistry:
    def __init__(self) -> None:
        self._channels: dict[str, PushChannel] = {}

    def register(self, channel: PushChannel) -> None:
        self._channels[channel.name] = channel

    def get(self, name: str) -> PushChannel:
        try:
            return self._channels[name]
        except KeyError as exc:
            raise ValueError(f"Push channel is not registered: {name}") from exc

