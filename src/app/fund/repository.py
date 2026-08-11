from typing import Protocol, TypeVar

from pydantic import BaseModel

from .contracts import (
    FundCatalog,
    FundEstimateRecord,
    FundHistoryRange,
    FundHoldingsSnapshot,
    FundNavHistoryResponse,
    FundNavRecord,
    FundProfile,
)


class AsyncKeyValueStore(Protocol):
    async def get(self, key: str) -> str | bytes | None: ...

    async def set(self, key: str, value: str, *, ex: int) -> object: ...


CacheModel = TypeVar("CacheModel", bound=BaseModel)


class FundCacheRepository:
    def __init__(
        self,
        store: AsyncKeyValueStore,
        *,
        catalog_ttl_seconds: int = 21_600,
        nav_ttl_seconds: int = 1_800,
        holdings_ttl_seconds: int = 21_600,
        valuation_ttl_seconds: int = 20,
        nav_history_ttl_seconds: int = 1800,
        last_valid_nav_ttl_seconds: int = 2_592_000,
    ) -> None:
        self.store = store
        self.catalog_ttl_seconds = catalog_ttl_seconds
        self.nav_ttl_seconds = nav_ttl_seconds
        self.holdings_ttl_seconds = holdings_ttl_seconds
        self.valuation_ttl_seconds = valuation_ttl_seconds
        self.nav_history_ttl_seconds = nav_history_ttl_seconds
        self.last_valid_nav_ttl_seconds = last_valid_nav_ttl_seconds

    async def get_catalog(self) -> list[FundProfile]:
        value = await self.store.get("fund:catalog")
        if value is None:
            return []
        try:
            return FundCatalog.model_validate_json(value).items
        except (ValueError, TypeError):
            return []

    async def set_catalog(self, items: list[FundProfile]) -> None:
        await self._set(
            "fund:catalog",
            FundCatalog(items=items),
            self.catalog_ttl_seconds,
        )

    async def get_profile(self, code: str) -> FundProfile | None:
        return await self._get(f"fund:profile:{code}", FundProfile)

    async def set_profile(self, profile: FundProfile) -> None:
        await self._set(
            f"fund:profile:{profile.code}",
            profile,
            self.catalog_ttl_seconds,
        )

    async def get_nav(self, code: str) -> FundNavRecord | None:
        return await self._get(f"fund:nav:{code}", FundNavRecord)

    async def set_nav(self, value: FundNavRecord) -> None:
        await self._set(f"fund:nav:{value.code}", value, self.nav_ttl_seconds)
        if value.data.value is not None and not value.data.is_estimate:
            await self._set(
                f"fund:last-valid-nav:{value.code}",
                value,
                self.last_valid_nav_ttl_seconds,
            )

    async def get_last_valid_nav(self, code: str) -> FundNavRecord | None:
        value = await self._get(f"fund:last-valid-nav:{code}", FundNavRecord)
        if value is None or value.data.value is None or value.data.is_estimate:
            return None
        return value

    async def get_holdings(self, code: str) -> FundHoldingsSnapshot | None:
        return await self._get(f"fund:holdings:{code}", FundHoldingsSnapshot)

    async def set_holdings(self, value: FundHoldingsSnapshot) -> None:
        await self._set(f"fund:holdings:{value.code}", value, self.holdings_ttl_seconds)

    async def get_valuation(self, code: str) -> FundEstimateRecord | None:
        return await self._get(f"fund:valuation:{code}", FundEstimateRecord)

    async def set_valuation(self, value: FundEstimateRecord) -> None:
        await self._set(f"fund:valuation:{value.code}", value, self.valuation_ttl_seconds)

    async def get_nav_history(
        self,
        code: str,
        history_range: FundHistoryRange,
    ) -> FundNavHistoryResponse | None:
        return await self._get(
            f"fund:nav-history:{code}:{history_range}",
            FundNavHistoryResponse,
        )

    async def set_nav_history(self, value: FundNavHistoryResponse) -> None:
        await self._set(
            f"fund:nav-history:{value.code}:{value.range}",
            value,
            self.nav_history_ttl_seconds,
        )

    async def _get(self, key: str, model: type[CacheModel]) -> CacheModel | None:
        value = await self.store.get(key)
        if value is None:
            return None
        try:
            return model.model_validate_json(value)
        except (ValueError, TypeError):
            return None

    async def _set(self, key: str, value: BaseModel, ttl_seconds: int) -> None:
        await self.store.set(key, value.model_dump_json(), ex=ttl_seconds)
