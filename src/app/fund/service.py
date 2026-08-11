import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID

from app.db.models import FundPosition
from app.db.repositories import FundPositionRepository, FundWatchlistRepository

from .contracts import (
    FundDetail,
    FundDetailView,
    FundEstimateRecord,
    FundHistoryRange,
    FundHoldingsSnapshot,
    FundMarketStatus,
    FundMutationResponse,
    FundNavHistoryResponse,
    FundNavRecord,
    FundPositionInput,
    FundPositionView,
    FundProfile,
    FundProvider,
    FundProviderError,
    FundProviderUnauthorizedError,
    FundSearchResponse,
    FundValuationProvider,
    FundValue,
    FundWatchlistItem,
    FundWatchlistResponse,
    HistoricalFundProvider,
)
from .repository import FundCacheRepository
from .trading_hours import fund_market_status

logger = logging.getLogger(__name__)


class FundService:
    def __init__(
        self,
        provider: FundProvider,
        valuation_provider: FundValuationProvider,
        cache: FundCacheRepository,
        watchlists: FundWatchlistRepository,
        positions: FundPositionRepository,
        user_id: UUID,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.provider = provider
        self.valuation_provider = valuation_provider
        self.cache = cache
        self.watchlists = watchlists
        self.positions = positions
        self.user_id = user_id
        self.now = now or (lambda: datetime.now(UTC))

    async def search(self, query: str, limit: int, refresh: bool = False) -> FundSearchResponse:
        items = [] if refresh else await self.cache.get_catalog()
        message = None
        if not items and self.provider.configured:
            try:
                items = await self.provider.catalog()
            except FundProviderError as exc:
                logger.warning("fund_catalog_unavailable error_type=%s", type(exc).__name__)
                message = self._provider_message()
            else:
                if items:
                    await self.cache.set_catalog(items)
        elif not self.provider.configured:
            message = self._provider_message()

        normalized = query.strip().casefold()
        matches = [
            item
            for item in items
            if normalized in item.code.casefold() or normalized in item.name.casefold()
        ][:limit]
        if not matches and normalized.isdigit() and len(normalized) == 6:
            code = f"{normalized}.OF"
            estimate = (await self._load_estimates([code], refresh)).get(code)
            if estimate is not None and estimate.name:
                matches = [
                    FundProfile(
                        code=code,
                        name=estimate.name,
                        source=self.valuation_provider.name,
                    )
                ]
        return FundSearchResponse(
            items=matches,
            provider_configured=self.provider.configured,
            experimental_valuation_enabled=self.valuation_provider.enabled,
            message=message,
        )

    async def nav_history(
        self,
        code: str,
        history_range: FundHistoryRange,
        refresh: bool = False,
    ) -> FundNavHistoryResponse:
        cached = None if refresh else await self.cache.get_nav_history(code, history_range)
        if cached is not None:
            return cached
        if not self.provider.configured:
            return FundNavHistoryResponse(
                code=code,
                range=history_range,
                items=[],
                source=self.provider.name,
                as_of=None,
                is_estimate=False,
                status="unauthorized",
                message="历史净值数据源未授权",
            )
        try:
            history_provider = cast(HistoricalFundProvider, self.provider)
            result = await history_provider.nav_history(code, history_range)
        except FundProviderUnauthorizedError:
            logger.warning("fund_nav_history_unauthorized code=%s", code)
            result = FundNavHistoryResponse(
                code=code,
                range=history_range,
                items=[],
                source=self.provider.name,
                as_of=None,
                is_estimate=False,
                status="unauthorized",
                message="历史净值数据源未授权",
            )
        except FundProviderError as exc:
            logger.warning(
                "fund_nav_history_unavailable code=%s error_type=%s",
                code,
                type(exc).__name__,
            )
            result = FundNavHistoryResponse(
                code=code,
                range=history_range,
                items=[],
                source=self.provider.name,
                as_of=None,
                is_estimate=False,
                status="error",
                message="历史净值数据暂时不可用",
            )
        await self.cache.set_nav_history(result)
        return result

    async def detail(self, code: str, refresh: bool = False) -> FundDetailView | None:
        official_task = asyncio.create_task(self._load_official(code, refresh))
        estimates_task = asyncio.create_task(self._load_estimates([code], refresh))
        official, estimates = await asyncio.gather(official_task, estimates_task)
        profile, nav, holdings, unavailable = official
        estimate = estimates.get(code) or self._missing_estimate(code)
        if profile is None and estimate.name:
            profile = FundProfile(code=code, name=estimate.name, source=estimate.data.source)
        if profile is None and not unavailable:
            return None
        profile = profile or self._unavailable_profile(code)
        detail = self._detail(profile, nav, holdings)
        position = await self.positions.for_user_code(self.user_id, code)
        status = fund_market_status(self.now())
        official_nav = self._present_official_nav(
            self._published_nav_or(nav.data, estimate),
            status,
        )
        return FundDetailView(
            **detail.model_dump(),
            provider_configured=self.provider.configured,
            experimental_valuation_enabled=self.valuation_provider.enabled,
            market_status=status,
            official_nav=official_nav,
            intraday_estimate=estimate.data,
            estimate_change_percent=estimate.change_percent,
            is_favorite=await self.watchlists.contains(self.user_id, code),
            position=self._position_view(position, official_nav, estimate.data),
        )

    async def watchlist(self, refresh: bool = False) -> FundWatchlistResponse:
        favorites = await self.watchlists.for_user(self.user_id)
        codes = [favorite.fund_code for favorite in favorites]
        positions = {
            position.fund_code: position for position in await self.positions.for_user(self.user_id)
        }
        estimates_task = asyncio.create_task(self._load_estimates(codes, refresh))
        official_results = await asyncio.gather(
            *(self._load_official(code, refresh) for code in codes)
        )
        estimates = await estimates_task
        items: list[FundWatchlistItem] = []
        any_unavailable = False
        status = fund_market_status(self.now())
        for code, official in zip(codes, official_results, strict=True):
            profile, nav, _holdings, unavailable = official
            estimate = estimates.get(code) or self._missing_estimate(code)
            any_unavailable = any_unavailable or unavailable
            if profile is None and estimate.name:
                profile = FundProfile(code=code, name=estimate.name, source=estimate.data.source)
            profile = profile or self._unavailable_profile(code)
            official_nav = self._present_official_nav(
                self._published_nav_or(nav.data, estimate),
                status,
            )
            items.append(
                FundWatchlistItem(
                    **profile.model_dump(),
                    latest_nav=official_nav.value,
                    nav_date=(
                        official_nav.as_of
                        if not isinstance(official_nav.as_of, datetime)
                        else None
                    ),
                    market_status=status,
                    official_nav=official_nav,
                    intraday_estimate=estimate.data,
                    estimate_change_percent=estimate.change_percent,
                    position=self._position_view(
                        positions.get(code),
                        official_nav,
                        estimate.data,
                    ),
                )
            )
        return FundWatchlistResponse(
            items=items,
            provider_configured=self.provider.configured,
            experimental_valuation_enabled=self.valuation_provider.enabled,
            generated_at=self.now(),
            message=self._provider_message() if any_unavailable else None,
        )

    async def add_watchlist(self, code: str) -> FundMutationResponse:
        await self.watchlists.add_code(self.user_id, code)
        return FundMutationResponse(fund_code=code, status="saved")

    async def remove_watchlist(self, code: str) -> FundMutationResponse:
        await self.watchlists.remove_code(self.user_id, code)
        return FundMutationResponse(fund_code=code, status="deleted")

    async def save_position(
        self,
        code: str,
        value: FundPositionInput,
    ) -> FundMutationResponse:
        await self.positions.save(
            self.user_id,
            code,
            Decimal(str(value.shares)),
            Decimal(str(value.average_cost)),
        )
        await self.watchlists.add_code(self.user_id, code)
        return FundMutationResponse(fund_code=code, status="saved")

    async def remove_position(self, code: str) -> FundMutationResponse:
        await self.positions.remove(self.user_id, code)
        return FundMutationResponse(fund_code=code, status="deleted")

    async def _load_official(
        self,
        code: str,
        refresh: bool,
    ) -> tuple[FundProfile | None, FundNavRecord, FundHoldingsSnapshot, bool]:
        if not self.provider.configured:
            missing_nav = self._missing_nav(code)
            last_valid_nav = await self._last_valid_nav_or(missing_nav, code)
            return None, last_valid_nav, self._missing_holdings(code), True
        profile, nav, holdings = await asyncio.gather(
            self._load_profile(code, refresh),
            self._load_nav(code, refresh),
            self._load_holdings(code, refresh),
        )
        unavailable = any(value[1] for value in (profile, nav, holdings))
        return (
            profile[0],
            nav[0] or self._missing_nav(code),
            holdings[0] or self._missing_holdings(code),
            unavailable,
        )

    async def _load_profile(
        self,
        code: str,
        refresh: bool,
    ) -> tuple[FundProfile | None, bool]:
        if not refresh:
            cached = await self.cache.get_profile(code)
            if cached is not None:
                return cached, False
        try:
            profile = await self.provider.profile(code)
        except FundProviderError as exc:
            self._log_official_error("profile", code, exc)
            return None, True
        if profile is not None:
            await self.cache.set_profile(profile)
        return profile, False

    async def _load_nav(
        self,
        code: str,
        refresh: bool,
    ) -> tuple[FundNavRecord | None, bool]:
        if not refresh:
            cached = await self.cache.get_nav(code)
            if cached is not None:
                return cached, False
        try:
            value = await self.provider.official_nav(code)
        except FundProviderError as exc:
            self._log_official_error("nav", code, exc)
            cached = await self.cache.get_last_valid_nav(code)
            if cached is not None:
                cached = cached.model_copy(
                    update={"data": cached.data.model_copy(update={"is_stale": True})}
                )
            return cached, True
        await self.cache.set_nav(value)
        return value, False

    async def _last_valid_nav_or(self, fallback: FundNavRecord, code: str) -> FundNavRecord:
        cached = await self.cache.get_last_valid_nav(code)
        if cached is None:
            return fallback
        return cached.model_copy(
            update={"data": cached.data.model_copy(update={"is_stale": True})}
        )

    async def _load_holdings(
        self,
        code: str,
        refresh: bool,
    ) -> tuple[FundHoldingsSnapshot | None, bool]:
        if not refresh:
            cached = await self.cache.get_holdings(code)
            if cached is not None:
                return cached, False
        try:
            value = await self.provider.holdings(code)
        except FundProviderError as exc:
            self._log_official_error("holdings", code, exc)
            return None, True
        await self.cache.set_holdings(value)
        return value, False

    async def _load_estimates(
        self,
        codes: list[str],
        refresh: bool,
    ) -> dict[str, FundEstimateRecord]:
        if not self.valuation_provider.enabled:
            return {code: self._missing_estimate(code) for code in codes}
        result: dict[str, FundEstimateRecord] = {}
        missing: list[str] = []
        for code in codes:
            cached = None if refresh else await self.cache.get_valuation(code)
            if cached is None:
                missing.append(code)
            else:
                result[code] = cached
        if missing:
            try:
                fetched = await self.valuation_provider.fetch(missing)
            except FundProviderError as exc:
                logger.warning(
                    "experimental_fund_valuation_unavailable error_type=%s",
                    type(exc).__name__,
                )
                fetched = {}
            for code in missing:
                value = fetched.get(code) or self._missing_estimate(code)
                result[code] = value
                await self.cache.set_valuation(value)
        return result

    def _empty_official(
        self,
        code: str,
        *,
        unavailable: bool,
    ) -> tuple[FundProfile | None, FundNavRecord, FundHoldingsSnapshot, bool]:
        return None, self._missing_nav(code), self._missing_holdings(code), unavailable

    def _provider_message(self) -> str:
        if not self.provider.configured:
            return "Tushare 尚未配置，历史净值和季度重仓股暂无数据"
        return "Tushare 权限不足，历史净值或季度重仓股可能缺失"

    def _missing_estimate(self, code: str) -> FundEstimateRecord:
        return FundEstimateRecord(
            code=code,
            data=FundValue(
                value=None,
                source=self.valuation_provider.name,
                as_of=None,
                is_estimate=True,
                is_stale=True,
            ),
        )

    def _missing_nav(self, code: str) -> FundNavRecord:
        return FundNavRecord(
            code=code,
            data=FundValue(
                value=None,
                source=self.provider.name,
                as_of=None,
                is_estimate=False,
                is_stale=False,
            ),
        )

    def _missing_holdings(self, code: str) -> FundHoldingsSnapshot:
        return FundHoldingsSnapshot(
            code=code,
            source=self.provider.name,
            as_of=None,
            is_stale=False,
        )

    @staticmethod
    def _unavailable_profile(code: str) -> FundProfile:
        return FundProfile(code=code, name=code, source="暂无正式数据源")

    @staticmethod
    def _detail(
        profile: FundProfile,
        nav: FundNavRecord,
        holdings: FundHoldingsSnapshot,
    ) -> FundDetail:
        nav_date = nav.data.as_of if not isinstance(nav.data.as_of, datetime) else None
        return FundDetail(
            **profile.model_dump(),
            latest_nav=nav.data.value,
            nav_date=nav_date,
            holdings=holdings.items,
            holdings_report_date=holdings.as_of,
            holdings_source=holdings.source,
        )

    @staticmethod
    def _present_official_nav(value: FundValue, status: FundMarketStatus) -> FundValue:
        if value.value is None or status == "trading":
            return value
        return value.model_copy(update={"is_stale": True})

    @staticmethod
    def _published_nav_or(official: FundValue, estimate: FundEstimateRecord) -> FundValue:
        if official.value is not None:
            return official
        published = estimate.published_nav
        if (
            published is None
            or published.value is None
            or published.is_estimate
            or published.is_stale
        ):
            return official
        return published

    @staticmethod
    def _position_view(
        position: FundPosition | None,
        official_nav: FundValue,
        estimate: FundValue,
    ) -> FundPositionView | None:
        if position is None:
            return None
        shares = Decimal(position.shares)
        average_cost = Decimal(position.average_cost)
        official = FundService._calculate_position(shares, average_cost, official_nav.value)
        reliable_estimate = estimate.value if not estimate.is_stale else None
        estimated = FundService._calculate_position(shares, average_cost, reliable_estimate)
        return FundPositionView(
            shares=float(shares),
            average_cost=float(average_cost),
            official_market_value=official[0],
            official_profit=official[1],
            official_profit_rate=official[2],
            estimated_market_value=estimated[0],
            estimated_profit=estimated[1],
            estimated_profit_rate=estimated[2],
        )

    @staticmethod
    def _calculate_position(
        shares: Decimal,
        average_cost: Decimal,
        value: float | None,
    ) -> tuple[float | None, float | None, float | None]:
        if value is None:
            return None, None, None
        price = Decimal(str(value))
        market_value = shares * price
        cost = shares * average_cost
        profit = market_value - cost
        profit_rate = profit / cost * 100 if cost else None
        return (
            round(float(market_value), 2),
            round(float(profit), 2),
            round(float(profit_rate), 2) if profit_rate is not None else None,
        )

    @staticmethod
    def _log_official_error(part: str, code: str, exc: Exception) -> None:
        logger.warning(
            "fund_official_data_unavailable part=%s code=%s error_type=%s",
            part,
            code,
            type(exc).__name__,
        )
