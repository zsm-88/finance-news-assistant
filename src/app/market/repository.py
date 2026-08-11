from typing import Protocol

from .contracts import HistoryPeriod, HistoryRange, MarketHistoryResponse, MarketQuote


class AsyncKeyValueStore(Protocol):
    async def get(self, key: str) -> str | bytes | None: ...

    async def set(self, key: str, value: str, *, ex: int) -> object: ...


class MarketCacheRepository:
    def __init__(
        self,
        store: AsyncKeyValueStore,
        ttl_seconds: int = 60,
        last_valid_ttl_seconds: int = 2_592_000,
    ) -> None:
        self.store = store
        self.ttl_seconds = ttl_seconds
        self.last_valid_ttl_seconds = last_valid_ttl_seconds

    async def get(self, symbol: str) -> MarketQuote | None:
        value = await self.store.get(self._key(symbol))
        if value is None:
            return None
        try:
            return MarketQuote.model_validate_json(value)
        except (ValueError, TypeError):
            return None

    async def set(self, quote: MarketQuote) -> None:
        await self.store.set(
            self._key(quote.symbol),
            quote.model_dump_json(),
            ex=self.ttl_seconds,
        )
        if quote.price is not None and quote.timestamp is not None:
            await self.store.set(
                self._last_valid_key(quote.symbol),
                quote.model_dump_json(),
                ex=self.last_valid_ttl_seconds,
            )

    async def get_last_valid(self, symbol: str) -> MarketQuote | None:
        value = await self.store.get(self._last_valid_key(symbol))
        if value is None:
            return None
        try:
            quote = MarketQuote.model_validate_json(value)
        except (ValueError, TypeError):
            return None
        return quote if quote.price is not None and quote.timestamp is not None else None

    @staticmethod
    def _key(symbol: str) -> str:
        return f"market:{symbol}"

    @staticmethod
    def _last_valid_key(symbol: str) -> str:
        return f"market:last-valid:{symbol}"


class MarketHistoryCacheRepository:
    def __init__(self, store: AsyncKeyValueStore, ttl_seconds: int = 900) -> None:
        self.store = store
        self.ttl_seconds = ttl_seconds

    async def get(
        self,
        symbol: str,
        period: HistoryPeriod,
        history_range: HistoryRange,
    ) -> MarketHistoryResponse | None:
        value = await self.store.get(self._key(symbol, period, history_range))
        if value is None:
            return None
        try:
            return MarketHistoryResponse.model_validate_json(value)
        except (ValueError, TypeError):
            return None

    async def set(self, value: MarketHistoryResponse) -> None:
        await self.store.set(
            self._key(value.symbol, value.period, value.range),
            value.model_dump_json(),
            ex=self.ttl_seconds,
        )

    @staticmethod
    def _key(symbol: str, period: HistoryPeriod, history_range: HistoryRange) -> str:
        return f"market:history:{symbol}:{period}:{history_range}"
