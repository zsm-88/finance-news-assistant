from .base import AIProvider
from .registry import ProviderRegistry


class ProviderRouter:
    def __init__(self, registry: ProviderRegistry, default_provider: str) -> None:
        self.registry = registry
        self.default_provider = default_provider

    def route(self, provider: str | None = None) -> AIProvider:
        return self.registry.get(provider or self.default_provider)

