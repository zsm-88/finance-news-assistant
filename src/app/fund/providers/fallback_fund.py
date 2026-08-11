from collections.abc import Awaitable, Callable
from typing import TypeVar, cast

from ..contracts import (
    FundHistoryRange,
    FundHoldingsSnapshot,
    FundNavHistoryResponse,
    FundNavRecord,
    FundProfile,
    FundProvider,
    FundProviderError,
    HistoricalFundProvider,
)

ResultT = TypeVar("ResultT")


class FallbackFundProvider:
    def __init__(
        self,
        primary: FundProvider,
        fallback: FundProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = f"{primary.name} / {fallback.name}"

    @property
    def configured(self) -> bool:
        return self.primary.configured or self.fallback.configured

    async def catalog(self) -> list[FundProfile]:
        return await self._call(lambda: self.primary.catalog(), lambda: self.fallback.catalog())

    async def profile(self, code: str) -> FundProfile | None:
        result = await self._call(
            lambda: self.primary.profile(code),
            lambda: self.fallback.profile(code),
        )
        if result is None and self.fallback.configured:
            return await self.fallback.profile(code)
        return result

    async def official_nav(self, code: str) -> FundNavRecord:
        result = await self._call(
            lambda: self.primary.official_nav(code),
            lambda: self.fallback.official_nav(code),
        )
        if result.data.value is None and self.fallback.configured:
            return await self.fallback.official_nav(code)
        return result

    async def holdings(self, code: str) -> FundHoldingsSnapshot:
        result = await self._call(
            lambda: self.primary.holdings(code),
            lambda: self.fallback.holdings(code),
        )
        if not result.items and result.as_of is None and self.fallback.configured:
            return await self.fallback.holdings(code)
        return result

    async def nav_history(
        self,
        code: str,
        history_range: FundHistoryRange,
    ) -> FundNavHistoryResponse:
        primary = self.primary
        fallback = self.fallback
        result = await self._call(
            lambda: self._history(primary, code, history_range),
            lambda: self._history(fallback, code, history_range),
        )
        if result.status != "available" and fallback.configured:
            return await self._history(fallback, code, history_range)
        return result

    async def _call(
        self,
        primary_call: Callable[[], Awaitable[ResultT]],
        fallback_call: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        if self.primary.configured:
            try:
                return await primary_call()
            except FundProviderError:
                if not self.fallback.configured:
                    raise
        if self.fallback.configured:
            return await fallback_call()
        return await primary_call()

    @staticmethod
    async def _history(
        provider: FundProvider,
        code: str,
        history_range: FundHistoryRange,
    ) -> FundNavHistoryResponse:
        historical = cast(HistoricalFundProvider, provider)
        return await historical.nav_history(code, history_range)
