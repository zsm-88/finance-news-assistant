import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import httpx

from ..contracts import FundEstimateRecord, FundProviderError, FundValue
from ..trading_hours import estimate_is_stale

logger = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")
FIELDS = "FCODE,SHORTNAME,GSZZL,GZTIME,GSZ,NAV,PDATE"


class EastmoneyFundValuationProvider:
    name = "天天基金实验性估值"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        enabled: bool,
        base_url: str = "https://fundcomapi.tiantianfunds.com",
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
        original_by_raw = {self._raw_code(code): code for code in codes}
        try:
            response = await self.client.get(
                f"{self.base_url}/mm/newCore/FundValuationLast",
                params={"FCODES": ",".join(original_by_raw), "FIELDS": FIELDS},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "experimental_fund_valuation_request_failed error_type=%s",
                type(exc).__name__,
            )
            raise FundProviderError("Experimental fund valuation request failed") from exc
        if payload.get("success") is not True:
            raise FundProviderError("Experimental fund valuation provider returned failure")

        current = self.now()
        records: dict[str, FundEstimateRecord] = {}
        items = payload.get("data") if isinstance(payload.get("data"), list) else []
        for item in items:
            if not isinstance(item, dict):
                continue
            raw_code = str(item.get("FCODE") or "").strip()
            code = original_by_raw.get(raw_code)
            if code is None:
                continue
            value = self._number(item.get("GSZ"))
            as_of = self._datetime(item.get("GZTIME"))
            published_nav_value = self._number(item.get("NAV"))
            published_nav_date = self._date(item.get("PDATE"))
            records[code] = FundEstimateRecord(
                code=code,
                name=self._text(item.get("SHORTNAME")),
                data=FundValue(
                    value=value,
                    source=self.name,
                    as_of=as_of,
                    is_estimate=True,
                    is_stale=value is None
                    or estimate_is_stale(as_of, current, self.stale_after_seconds),
                ),
                change_percent=self._number(item.get("GSZZL")),
                published_nav=FundValue(
                    value=published_nav_value,
                    source="天天基金最新公布净值",
                    as_of=published_nav_date,
                    is_estimate=False,
                    is_stale=published_nav_value is None or published_nav_date is None,
                ),
            )
        return records

    @staticmethod
    def _raw_code(code: str) -> str:
        return code.split(".", maxsplit=1)[0]

    @staticmethod
    def _datetime(value: object) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            local = datetime.fromisoformat(str(value)).replace(tzinfo=SHANGHAI)
        except ValueError:
            return None
        return local.astimezone(UTC)

    @staticmethod
    def _date(value: object) -> date | None:
        if value in (None, ""):
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _number(value: object) -> float | None:
        if value in (None, ""):
            return None
        try:
            return float(str(value))
        except ValueError:
            return None

    @staticmethod
    def _text(value: object) -> str | None:
        return str(value) if value not in (None, "") else None
