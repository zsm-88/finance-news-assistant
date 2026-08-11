import logging

from ..contracts import FundEstimateRecord, FundProviderError, FundValuationProvider

logger = logging.getLogger(__name__)


class FallbackFundValuationProvider:
    name = "实验性盘中估值"

    def __init__(
        self,
        primary: FundValuationProvider,
        fallback: FundValuationProvider,
    ) -> None:
        self.primary = primary
        self.fallback = fallback

    @property
    def enabled(self) -> bool:
        return self.primary.enabled or self.fallback.enabled

    async def fetch(self, codes: list[str]) -> dict[str, FundEstimateRecord]:
        primary_values = await self._fetch_safely(self.primary, codes)
        missing = [
            code
            for code in codes
            if code not in primary_values or primary_values[code].data.value is None
        ]
        fallback_values = await self._fetch_safely(self.fallback, missing)
        results = dict(primary_values)
        for code, fallback_value in fallback_values.items():
            primary_value = primary_values.get(code)
            if primary_value is not None:
                fallback_value = fallback_value.model_copy(
                    update={
                        "name": primary_value.name or fallback_value.name,
                        "published_nav": (
                            primary_value.published_nav or fallback_value.published_nav
                        ),
                    }
                )
            results[code] = fallback_value
        return results

    @staticmethod
    async def _fetch_safely(
        provider: FundValuationProvider,
        codes: list[str],
    ) -> dict[str, FundEstimateRecord]:
        if not provider.enabled or not codes:
            return {}
        try:
            return await provider.fetch(codes)
        except FundProviderError as exc:
            logger.warning(
                "experimental_fund_valuation_source_failed source=%s error_type=%s",
                provider.name,
                type(exc).__name__,
            )
            return {}
