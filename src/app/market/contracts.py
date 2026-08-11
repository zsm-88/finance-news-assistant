from collections.abc import Sequence
from datetime import datetime
from typing import Literal, Protocol, Self

from pydantic import BaseModel, Field, model_validator

MarketStatus = Literal[
    "trading",
    "closed",
    "weekend",
    "holiday",
    "pre_market",
    "post_market",
    "unavailable",
]
HistoryPeriod = Literal["intraday", "day", "week", "month"]
HistoryRange = Literal["1d", "1m", "3m", "6m", "1y", "5y"]
HistoryStatus = Literal["available", "unavailable", "error"]


class MarketProviderError(RuntimeError):
    pass


class MarketInstrument(BaseModel, frozen=True):
    symbol: str
    provider_symbol: str
    name: str
    market: str
    asset_type: str


class MarketQuote(BaseModel):
    symbol: str
    name: str
    market: str
    asset_type: str
    price: float | None
    change: float | None
    change_percent: float | None
    timestamp: datetime | None
    market_status: MarketStatus
    source: str
    is_delayed: bool = False
    is_stale: bool = False


class MarketProvider(Protocol):
    name: str

    async def fetch(
        self,
        instruments: Sequence[MarketInstrument],
    ) -> dict[str, MarketQuote]: ...


class MarketHistoryPoint(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = Field(default=None, ge=0)
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None

    @model_validator(mode="after")
    def validate_candle(self) -> Self:
        if self.timestamp.utcoffset() is None:
            raise ValueError("History timestamp must include timezone")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("History high is below candle values")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("History low is above candle values")
        return self


class MarketHistoryResponse(BaseModel):
    symbol: str
    name: str
    period: HistoryPeriod
    range: HistoryRange
    items: list[MarketHistoryPoint]
    source: str
    as_of: datetime | None
    is_delayed: bool
    timezone: str
    status: HistoryStatus
    message: str | None = None

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        timestamps = [item.timestamp for item in self.items]
        if timestamps != sorted(timestamps):
            raise ValueError("History points must be ordered by timestamp")
        return self


class HistoricalMarketProvider(Protocol):
    name: str

    def supports(self, instrument: MarketInstrument, period: HistoryPeriod) -> bool: ...

    async def fetch_history(
        self,
        instrument: MarketInstrument,
        period: HistoryPeriod,
        history_range: HistoryRange,
    ) -> MarketHistoryResponse: ...


class MarketListResponse(BaseModel):
    items: list[MarketQuote]
    generated_at: datetime
    cache_ttl_seconds: int
