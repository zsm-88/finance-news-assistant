from datetime import date, datetime
from typing import Literal, Protocol, Self

from pydantic import BaseModel, Field, model_validator

FundMarketStatus = Literal["trading", "closed", "weekend", "holiday", "unavailable"]
FundHistoryRange = Literal["1m", "3m", "6m", "1y"]
FundHistoryStatus = Literal["available", "unavailable", "unauthorized", "error"]


class FundProviderError(RuntimeError):
    pass


class FundProviderUnauthorizedError(FundProviderError):
    pass


class FundProfile(BaseModel):
    code: str
    name: str
    fund_type: str | None = None
    management_company: str | None = None
    source: str = "Tushare"


class FundValue(BaseModel):
    value: float | None
    source: str
    as_of: date | datetime | None
    is_estimate: bool
    is_stale: bool


class FundNavRecord(BaseModel):
    code: str
    data: FundValue


class FundNavHistoryPoint(BaseModel):
    nav_date: date
    unit_nav: float = Field(gt=0)
    adj_nav: float | None = Field(default=None, gt=0)


class FundNavHistoryResponse(BaseModel):
    code: str
    range: FundHistoryRange
    items: list[FundNavHistoryPoint]
    source: str
    as_of: date | None
    is_estimate: Literal[False] = False
    is_stale: bool = False
    status: FundHistoryStatus
    message: str | None = None

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        dates = [item.nav_date for item in self.items]
        if dates != sorted(dates):
            raise ValueError("Official NAV history must be ordered by date")
        return self


class FundEstimateRecord(BaseModel):
    code: str
    name: str | None = None
    data: FundValue
    change_percent: float | None = None
    published_nav: FundValue | None = None


class FundHolding(BaseModel):
    symbol: str
    name: str | None = None
    market_value: float | None = None
    shares: float | None = None
    weight_percent: float | None = None
    change_percent: float | None = None
    report_date: date


class FundHoldingsSnapshot(BaseModel):
    code: str
    items: list[FundHolding] = Field(default_factory=list)
    source: str
    as_of: date | None
    is_stale: bool = False


class FundDetail(FundProfile):
    latest_nav: float | None = None
    nav_date: date | None = None
    holdings: list[FundHolding] = Field(default_factory=list)
    holdings_report_date: date | None = None
    holdings_source: str | None = None


class FundCatalog(BaseModel):
    items: list[FundProfile]


class FundProvider(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    async def catalog(self) -> list[FundProfile]: ...

    async def profile(self, code: str) -> FundProfile | None: ...

    async def official_nav(self, code: str) -> FundNavRecord: ...

    async def holdings(self, code: str) -> FundHoldingsSnapshot: ...


class HistoricalFundProvider(Protocol):
    name: str

    @property
    def configured(self) -> bool: ...

    async def nav_history(
        self,
        code: str,
        history_range: FundHistoryRange,
    ) -> FundNavHistoryResponse: ...


class FundValuationProvider(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    async def fetch(self, codes: list[str]) -> dict[str, FundEstimateRecord]: ...


class FundSearchResponse(BaseModel):
    items: list[FundProfile]
    provider_configured: bool
    experimental_valuation_enabled: bool
    message: str | None = None


class FundPositionInput(BaseModel):
    shares: float = Field(gt=0, le=1_000_000_000_000)
    average_cost: float = Field(ge=0, le=1_000_000_000)


class FundPositionView(BaseModel):
    shares: float
    average_cost: float
    official_market_value: float | None
    official_profit: float | None
    official_profit_rate: float | None
    estimated_market_value: float | None
    estimated_profit: float | None
    estimated_profit_rate: float | None


class FundDetailView(FundDetail):
    provider_configured: bool
    experimental_valuation_enabled: bool
    market_status: FundMarketStatus
    official_nav: FundValue
    intraday_estimate: FundValue
    estimate_change_percent: float | None = None
    is_favorite: bool = False
    position: FundPositionView | None = None


class FundWatchlistItem(FundProfile):
    latest_nav: float | None = None
    nav_date: date | None = None
    market_status: FundMarketStatus
    official_nav: FundValue
    intraday_estimate: FundValue
    estimate_change_percent: float | None = None
    position: FundPositionView | None = None


class FundWatchlistResponse(BaseModel):
    items: list[FundWatchlistItem]
    provider_configured: bool
    experimental_valuation_enabled: bool
    generated_at: datetime
    message: str | None = None


class FundMutationResponse(BaseModel):
    fund_code: str
    status: Literal["saved", "deleted"]
