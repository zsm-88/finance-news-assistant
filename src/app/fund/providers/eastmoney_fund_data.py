import json
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from ..contracts import (
    FundHistoryRange,
    FundHolding,
    FundHoldingsSnapshot,
    FundNavHistoryPoint,
    FundNavHistoryResponse,
    FundNavRecord,
    FundProfile,
    FundProviderError,
    FundValue,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
HISTORY_SOURCE = "东方财富实验性历史净值"
HOLDINGS_SOURCE = "东方财富实验性季度重仓"


class EastmoneyExperimentalFundProvider:
    name = "东方财富实验性基金数据"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        enabled: bool,
        trend_base_url: str = "https://fund.eastmoney.com/pingzhongdata",
        mobile_base_url: str = "https://fundmobapi.eastmoney.com",
        today: Callable[[], date] | None = None,
    ) -> None:
        self.client = client
        self.enabled = enabled
        self.trend_base_url = trend_base_url.rstrip("/")
        self.mobile_base_url = mobile_base_url.rstrip("/")
        self.today = today or (lambda: datetime.now(UTC).astimezone(SHANGHAI).date())

    @property
    def configured(self) -> bool:
        return self.enabled

    async def catalog(self) -> list[FundProfile]:
        return []

    async def profile(self, code: str) -> FundProfile | None:
        payload = await self._trend_script(code)
        name = self._script_value(payload, "fS_name")
        if not isinstance(name, str) or not name.strip():
            return None
        return FundProfile(code=code, name=name.strip(), source=self.name)

    async def official_nav(self, code: str) -> FundNavRecord:
        payload = await self._trend_script(code)
        points = self._history_points(payload)
        latest = points[-1] if points else None
        return FundNavRecord(
            code=code,
            data=FundValue(
                value=latest.unit_nav if latest else None,
                source=HISTORY_SOURCE,
                as_of=latest.nav_date if latest else None,
                is_estimate=False,
                is_stale=False,
            ),
        )

    async def nav_history(
        self,
        code: str,
        history_range: FundHistoryRange,
    ) -> FundNavHistoryResponse:
        payload = await self._trend_script(code)
        points = self._history_points(payload)
        days = {"1m": 31, "3m": 93, "6m": 186, "1y": 366}[history_range]
        cutoff = self.today() - timedelta(days=days)
        items = [point for point in points if point.nav_date >= cutoff]
        return FundNavHistoryResponse(
            code=code,
            range=history_range,
            items=items,
            source=HISTORY_SOURCE,
            as_of=items[-1].nav_date if items else None,
            is_estimate=False,
            status="available" if items else "unavailable",
            message=None if items else "东方财富暂无该时间范围的历史净值",
        )

    async def holdings(self, code: str) -> FundHoldingsSnapshot:
        raw_code = self._raw_code(code)
        try:
            response = await self.client.get(
                f"{self.mobile_base_url}/FundMNewApi/FundMNInverstPosition",
                params={
                    "FCODE": raw_code,
                    "deviceid": "Wap",
                    "plat": "WAP",
                    "product": "EFund",
                    "version": "2.0.0",
                },
                headers={"Referer": f"https://fund.eastmoney.com/{raw_code}.html"},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FundProviderError("Eastmoney experimental holdings request failed") from exc
        if payload.get("Success") is not True:
            raise FundProviderError("Eastmoney experimental holdings returned failure")
        report_date = self._date(payload.get("Expansion"))
        rows = ((payload.get("Datas") or {}).get("fundStocks") or [])
        items: list[FundHolding] = []
        if report_date is not None and isinstance(rows, list):
            for row in rows[:10]:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("GPDM") or "").strip()
                if not symbol:
                    continue
                items.append(
                    FundHolding(
                        symbol=symbol,
                        name=self._text(row.get("GPJC")),
                        weight_percent=self._number(row.get("JZBL")),
                        report_date=report_date,
                    )
                )
        changes = await self._holding_changes([item.symbol for item in items])
        items = [
            item.model_copy(update={"change_percent": changes.get(item.symbol)})
            for item in items
        ]
        return FundHoldingsSnapshot(
            code=code,
            items=items,
            source=HOLDINGS_SOURCE,
            as_of=report_date,
            is_stale=True,
        )

    async def _holding_changes(self, symbols: list[str]) -> dict[str, float]:
        codes = {
            symbol: quote_code
            for symbol in symbols
            if (quote_code := self._quote_code(symbol)) is not None
        }
        if not codes:
            return {}
        try:
            response = await self.client.get(
                "https://qt.gtimg.cn/q=" + ",".join(codes.values()),
                headers={"Referer": "https://finance.qq.com/"},
            )
            response.raise_for_status()
            payload = response.content.decode("gb18030", errors="replace")
        except (httpx.HTTPError, LookupError):
            return {}
        changes_by_code: dict[str, float] = {}
        for match in re.finditer(r'v_([^=]+)="([^"]*)"', payload):
            fields = match.group(2).split("~")
            value = self._number(fields[32]) if len(fields) > 32 else None
            if value is not None:
                changes_by_code[match.group(1)] = value
        return {
            symbol: changes_by_code[quote_code]
            for symbol, quote_code in codes.items()
            if quote_code in changes_by_code
        }

    async def _trend_script(self, code: str) -> str:
        if not self.enabled:
            raise FundProviderError("Eastmoney experimental fund data is disabled")
        raw_code = self._raw_code(code)
        try:
            response = await self.client.get(
                f"{self.trend_base_url}/{raw_code}.js",
                headers={"Referer": f"https://fund.eastmoney.com/{raw_code}.html"},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise FundProviderError("Eastmoney experimental history request failed") from exc
        if "Data_netWorthTrend" not in response.text:
            raise FundProviderError("Eastmoney experimental history payload is invalid")
        return response.text

    def _history_points(self, payload: str) -> list[FundNavHistoryPoint]:
        unit_rows = self._script_value(payload, "Data_netWorthTrend")
        accumulated_rows = self._script_value(payload, "Data_ACWorthTrend")
        adjusted_by_date: dict[date, float] = {}
        if isinstance(accumulated_rows, list):
            for row in accumulated_rows:
                if not isinstance(row, list) or len(row) < 2:
                    continue
                day = self._timestamp_date(row[0])
                value = self._number(row[1])
                if day is not None and value is not None and value > 0:
                    adjusted_by_date[day] = value
        by_date: dict[date, FundNavHistoryPoint] = {}
        if isinstance(unit_rows, list):
            for row in unit_rows:
                if not isinstance(row, dict):
                    continue
                day = self._timestamp_date(row.get("x"))
                value = self._number(row.get("y"))
                if day is None or value is None or value <= 0:
                    continue
                by_date[day] = FundNavHistoryPoint(
                    nav_date=day,
                    unit_nav=value,
                    adj_nav=adjusted_by_date.get(day),
                )
        return [by_date[day] for day in sorted(by_date)]

    @staticmethod
    def _script_value(payload: str, variable: str) -> Any:
        match = re.search(rf"\bvar\s+{re.escape(variable)}\s*=\s*", payload)
        if match is None:
            return None
        try:
            value, _ = json.JSONDecoder().raw_decode(payload[match.end() :].lstrip())
        except (json.JSONDecodeError, TypeError):
            return None
        return value

    @staticmethod
    def _raw_code(code: str) -> str:
        return code.split(".", maxsplit=1)[0]

    @staticmethod
    def _quote_code(symbol: str) -> str | None:
        value = symbol.strip()
        if re.fullmatch(r"\d{5}", value):
            return f"hk{value}"
        if not re.fullmatch(r"\d{6}", value):
            return None
        if value.startswith("6"):
            return f"sh{value}"
        if value.startswith(("0", "3")):
            return f"sz{value}"
        if value.startswith(("4", "8")):
            return f"bj{value}"
        return None

    @staticmethod
    def _timestamp_date(value: object) -> date | None:
        number = EastmoneyExperimentalFundProvider._number(value)
        if number is None:
            return None
        try:
            return datetime.fromtimestamp(number / 1000, UTC).astimezone(SHANGHAI).date()
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _date(value: object) -> date | None:
        try:
            return date.fromisoformat(str(value)) if value else None
        except ValueError:
            return None

    @staticmethod
    def _number(value: object) -> float | None:
        try:
            return float(str(value)) if value not in (None, "") else None
        except ValueError:
            return None

    @staticmethod
    def _text(value: object) -> str | None:
        return str(value).strip() if value not in (None, "") else None
