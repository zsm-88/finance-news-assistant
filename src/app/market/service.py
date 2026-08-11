import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from .contracts import (
    HistoricalMarketProvider,
    HistoryPeriod,
    HistoryRange,
    HistoryStatus,
    MarketHistoryResponse,
    MarketInstrument,
    MarketListResponse,
    MarketProvider,
    MarketProviderError,
    MarketQuote,
)
from .instruments import INSTRUMENTS
from .market_hours import market_status
from .repository import MarketCacheRepository, MarketHistoryCacheRepository

logger = logging.getLogger(__name__)


class MarketService:
    def __init__(
        self,
        provider: MarketProvider,
        cache: MarketCacheRepository,
        instruments: Sequence[MarketInstrument] = INSTRUMENTS,
        history_provider: HistoricalMarketProvider | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.instruments = tuple(instruments)
        self.history_provider = history_provider
        self.now = now or (lambda: datetime.now(UTC))
        self.instrument_by_symbol = {
            instrument.symbol: instrument for instrument in self.instruments
        }

    def supports(self, symbol: str) -> bool:
        return symbol in self.instrument_by_symbol

    async def list_quotes(self) -> MarketListResponse:
        quotes = await self._load(self.instruments)
        return MarketListResponse(
            items=[quotes[item.symbol] for item in self.instruments],
            generated_at=datetime.now(UTC),
            cache_ttl_seconds=self.cache.ttl_seconds,
        )

    async def quote(self, symbol: str) -> MarketQuote | None:
        instrument = self.instrument_by_symbol.get(symbol)
        if instrument is None:
            return None
        return (await self._load((instrument,)))[symbol]

    async def _load(
        self,
        instruments: Sequence[MarketInstrument],
    ) -> dict[str, MarketQuote]:
        quotes: dict[str, MarketQuote] = {}
        missing: list[MarketInstrument] = []
        for instrument in instruments:
            cached = await self.cache.get(instrument.symbol)
            if cached is None:
                missing.append(instrument)
            else:
                quotes[instrument.symbol] = self._present(cached)

        if missing:
            try:
                fetched = await self.provider.fetch(missing)
            except MarketProviderError as exc:
                logger.warning("market_provider_failed error_type=%s", type(exc).__name__)
                fetched = {}
            for symbol, quote in fetched.items():
                await self.cache.set(quote)
                fetched[symbol] = self._present(quote)
            quotes.update(fetched)

        for instrument in instruments:
            if instrument.symbol not in quotes:
                fallback = await self._fallback(instrument)
                quotes[instrument.symbol] = fallback
                await self.cache.set(fallback)
        return quotes

    async def _fallback(self, instrument: MarketInstrument) -> MarketQuote:
        cached = await self.cache.get_last_valid(instrument.symbol)
        shanghai = ZoneInfo("Asia/Shanghai")
        if (
            cached is not None
            and cached.timestamp is not None
            and cached.timestamp.astimezone(shanghai).date()
            >= self.now().astimezone(shanghai).date()
        ):
            return self._stale(cached)
        if self.history_provider is None or not self.history_provider.supports(instrument, "day"):
            return self._stale(cached) if cached is not None else self._unavailable(instrument)
        try:
            history = await self.history_provider.fetch_history(instrument, "day", "1m")
        except MarketProviderError as exc:
            logger.warning(
                "market_last_valid_history_failed symbol=%s error_type=%s",
                instrument.symbol,
                type(exc).__name__,
            )
            return self._stale(cached) if cached is not None else self._unavailable(instrument)
        if not history.items:
            return self._stale(cached) if cached is not None else self._unavailable(instrument)
        latest = history.items[-1]
        previous = history.items[-2] if len(history.items) > 1 else None
        if previous is None:
            change = None
            change_percent = None
        else:
            change = latest.close - previous.close
            change_percent = change / previous.close * 100 if previous.close else None
        timestamp = datetime.combine(latest.timestamp.date(), time(15), shanghai)
        history_quote = MarketQuote(
            symbol=instrument.symbol,
            name=instrument.name,
            market=instrument.market,
            asset_type=instrument.asset_type,
            price=latest.close,
            change=round(change, 4) if change is not None else None,
            change_percent=round(change_percent, 4) if change_percent is not None else None,
            timestamp=timestamp,
            market_status=market_status(instrument.market, self.now()),
            source=history.source,
            is_delayed=True,
            is_stale=True,
        )
        if cached is not None and cached.timestamp is not None and cached.timestamp >= timestamp:
            return self._stale(cached)
        return history_quote

    def _stale(self, quote: MarketQuote) -> MarketQuote:
        return quote.model_copy(
            update={
                "market_status": market_status(quote.market, self.now()),
                "is_delayed": True,
                "is_stale": True,
            }
        )

    def _present(self, quote: MarketQuote) -> MarketQuote:
        if quote.price is None or quote.timestamp is None:
            return quote
        status = market_status(quote.market, self.now())
        closed = status in {"closed", "weekend", "holiday"}
        return quote.model_copy(
            update={
                "market_status": status,
                "is_delayed": quote.is_delayed or closed,
                "is_stale": quote.is_stale or closed,
            }
        )

    def _unavailable(self, instrument: MarketInstrument) -> MarketQuote:
        return MarketQuote(
            symbol=instrument.symbol,
            name=instrument.name,
            market=instrument.market,
            asset_type=instrument.asset_type,
            price=None,
            change=None,
            change_percent=None,
            timestamp=None,
            market_status="unavailable",
            source=self.provider.name,
        )


class MarketHistoryService:
    def __init__(
        self,
        provider: HistoricalMarketProvider,
        cache: MarketHistoryCacheRepository,
        instruments: Sequence[MarketInstrument] = INSTRUMENTS,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.instrument_by_symbol = {item.symbol: item for item in instruments}

    def supports_symbol(self, symbol: str) -> bool:
        return symbol in self.instrument_by_symbol

    async def history(
        self,
        symbol: str,
        period: HistoryPeriod,
        history_range: HistoryRange,
    ) -> MarketHistoryResponse | None:
        instrument = self.instrument_by_symbol.get(symbol)
        if instrument is None:
            return None
        cached = await self.cache.get(symbol, period, history_range)
        if cached is not None:
            return cached
        if not self.provider.supports(instrument, period):
            result = self._unavailable(instrument, period, history_range)
        else:
            try:
                result = await self.provider.fetch_history(instrument, period, history_range)
            except MarketProviderError as exc:
                logger.warning(
                    "market_history_provider_failed symbol=%s error_type=%s",
                    symbol,
                    type(exc).__name__,
                )
                result = self._unavailable(
                    instrument,
                    period,
                    history_range,
                    status="error",
                    message="历史行情数据暂时不可用",
                )
        await self.cache.set(result)
        return result

    def _unavailable(
        self,
        instrument: MarketInstrument,
        period: HistoryPeriod,
        history_range: HistoryRange,
        *,
        status: HistoryStatus = "unavailable",
        message: str = "当前标的暂无可靠的历史行情数据",
    ) -> MarketHistoryResponse:
        return MarketHistoryResponse(
            symbol=instrument.symbol,
            name=instrument.name,
            period=period,
            range=history_range,
            items=[],
            source=self.provider.name,
            as_of=None,
            is_delayed=True,
            timezone="Asia/Shanghai",
            status=status,
            message=message,
        )
