import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import httpx

from ..contracts import FundEstimateRecord, FundProviderError, FundValue
from ..trading_hours import estimate_is_stale

logger = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")


class SinaFundValuationProvider:
    """Optional experimental adapter for Sina's unauthenticated fund estimate endpoint."""

    name = "新浪财经实验性估值"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        enabled: bool,
        base_url: str = "https://stock.finance.sina.com.cn/fundInfo/api/openapi.php",
        stale_after_seconds: int = 600,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.client = client
        self._enabled = enabled
        self.base_url = base_url.rstrip("/")
        self.stale_after_seconds = stale_after_seconds
        self.now = now or (lambda: datetime.now(UTC))

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def fetch(self, codes: list[str]) -> dict[str, FundEstimateRecord]:
        if not self.enabled or not codes:
            return {}
        results = await asyncio.gather(
            *(self._fetch_one(code) for code in codes),
            return_exceptions=True,
        )
        records: dict[str, FundEstimateRecord] = {}
        for code, result in zip(codes, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "experimental_sina_fund_valuation_failed code=%s error_type=%s",
                    code,
                    type(result).__name__,
                )
            elif result is not None:
                records[code] = result
        return records

    async def _fetch_one(self, code: str) -> FundEstimateRecord | None:
        try:
            response = await self.client.get(
                f"{self.base_url}/FdFundService.getEstimateNetworthPic",
                params={"symbol": code.split(".", maxsplit=1)[0]},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FundProviderError("Experimental Sina valuation request failed") from exc
        points = payload.get("result", {}).get("data", {}).get("networth", [])
        if not isinstance(points, list):
            return None
        last = next((item for item in reversed(points) if isinstance(item, dict)), None)
        if last is None:
            return None
        value = self._number(last.get("pre_nav"))
        growth_rate = self._number(last.get("growthrate"))
        as_of = self._datetime(last.get("pre_date"), last.get("min_time"))
        if value is None and growth_rate is None:
            return None
        return FundEstimateRecord(
            code=code,
            data=FundValue(
                value=value,
                source=self.name,
                as_of=as_of,
                is_estimate=True,
                is_stale=value is None
                or estimate_is_stale(as_of, self.now(), self.stale_after_seconds),
            ),
            change_percent=round(growth_rate * 100, 4) if growth_rate is not None else None,
        )

    @staticmethod
    def _datetime(day: object, clock: object) -> datetime | None:
        if day in (None, "") or clock in (None, ""):
            return None
        try:
            local = datetime.fromisoformat(f"{day} {clock}").replace(tzinfo=SHANGHAI)
        except ValueError:
            return None
        return local.astimezone(UTC)

    @staticmethod
    def _number(value: object) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value))
        except ValueError:
            return None
