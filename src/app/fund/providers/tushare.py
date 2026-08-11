from datetime import UTC, date, datetime, timedelta
from typing import Any

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
    FundProviderUnauthorizedError,
    FundValue,
)


class TushareFundProvider:
    name = "Tushare"

    def __init__(
        self,
        client: httpx.AsyncClient,
        token: str | None,
        base_url: str = "https://api.tushare.pro",
    ) -> None:
        self.client = client
        self.token = token.strip() if token else None
        self.base_url = base_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def catalog(self) -> list[FundProfile]:
        rows = await self._call(
            "fund_basic",
            {"status": "L"},
            "ts_code,name,management,fund_type",
        )
        return [self._profile(row) for row in rows if row.get("ts_code") and row.get("name")]

    async def profile(self, code: str) -> FundProfile | None:
        rows = await self._call(
            "fund_basic",
            {"ts_code": code},
            "ts_code,name,management,fund_type",
        )
        return self._profile(rows[0]) if rows else None

    async def official_nav(self, code: str) -> FundNavRecord:
        rows = await self._call(
            "fund_nav",
            {"ts_code": code},
            "ts_code,nav_date,unit_nav",
        )
        dated_navs = [
            (self._date(row.get("nav_date")), self._number(row.get("unit_nav"))) for row in rows
        ]
        valid_navs = [(day, nav) for day, nav in dated_navs if day is not None and nav is not None]
        latest_day, latest_nav = max(
            valid_navs,
            default=(None, None),
            key=lambda item: item[0] or date.min,
        )
        return FundNavRecord(
            code=code,
            data=FundValue(
                value=latest_nav,
                source=self.name,
                as_of=latest_day,
                is_estimate=False,
                is_stale=False,
            ),
        )

    async def nav_history(
        self,
        code: str,
        history_range: FundHistoryRange,
    ) -> FundNavHistoryResponse:
        days = {"1m": 31, "3m": 93, "6m": 186, "1y": 366}[history_range]
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        rows = await self._call(
            "fund_nav",
            {
                "ts_code": code,
                "start_date": start.strftime("%Y%m%d"),
                "end_date": end.strftime("%Y%m%d"),
            },
            "ts_code,nav_date,unit_nav,adj_nav",
        )
        items: list[FundNavHistoryPoint] = []
        for row in rows:
            nav_date = self._date(row.get("nav_date"))
            unit_nav = self._number(row.get("unit_nav"))
            if nav_date is None or unit_nav is None or unit_nav <= 0:
                continue
            items.append(
                FundNavHistoryPoint(
                    nav_date=nav_date,
                    unit_nav=unit_nav,
                    adj_nav=self._number(row.get("adj_nav")),
                )
            )
        items.sort(key=lambda item: item.nav_date)
        return FundNavHistoryResponse(
            code=code,
            range=history_range,
            items=items,
            source=self.name,
            as_of=items[-1].nav_date if items else None,
            is_estimate=False,
            status="available" if items else "unavailable",
            message=None if items else "Tushare 暂无该时间范围的正式历史净值",
        )

    async def holdings(self, code: str) -> FundHoldingsSnapshot:
        rows = await self._call(
            "fund_portfolio",
            {"ts_code": code},
            "ts_code,ann_date,end_date,symbol,mkv,amount,stk_mkv_ratio",
        )
        report_dates = [self._date(row.get("end_date")) for row in rows]
        report_date = max((day for day in report_dates if day is not None), default=None)
        holdings: list[FundHolding] = []
        if report_date is not None:
            report_rows = [row for row in rows if self._date(row.get("end_date")) == report_date]
            report_rows.sort(
                key=lambda row: self._number(row.get("stk_mkv_ratio")) or 0,
                reverse=True,
            )
            holdings = [
                FundHolding(
                    symbol=str(row["symbol"]),
                    market_value=self._number(row.get("mkv")),
                    shares=self._number(row.get("amount")),
                    weight_percent=self._number(row.get("stk_mkv_ratio")),
                    report_date=report_date,
                )
                for row in report_rows[:10]
                if row.get("symbol")
            ]
        return FundHoldingsSnapshot(
            code=code,
            items=holdings,
            source=self.name,
            as_of=report_date,
        )

    async def _call(
        self,
        api_name: str,
        params: dict[str, str],
        fields: str,
    ) -> list[dict[str, Any]]:
        if not self.token:
            raise FundProviderError("Tushare token is not configured")
        try:
            response = await self.client.post(
                self.base_url,
                json={
                    "api_name": api_name,
                    "token": self.token,
                    "params": params,
                    "fields": fields,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FundProviderError(f"Tushare request failed for {api_name}") from exc
        if payload.get("code") != 0:
            message = str(payload.get("msg", "unknown error"))
            if payload.get("code") == 40203 or any(
                marker in message.lower() for marker in ("权限", "积分", "permission", "points")
            ):
                raise FundProviderUnauthorizedError(f"Tushare access denied for {api_name}")
            raise FundProviderError(f"Tushare rejected {api_name}: {message}")
        data = payload.get("data") or {}
        field_names = data.get("fields") or []
        return [dict(zip(field_names, row, strict=False)) for row in data.get("items") or []]

    def _profile(self, row: dict[str, Any]) -> FundProfile:
        return FundProfile(
            code=str(row["ts_code"]),
            name=str(row["name"]),
            fund_type=self._text(row.get("fund_type")),
            management_company=self._text(row.get("management")),
            source=self.name,
        )

    @staticmethod
    def _date(value: object) -> date | None:
        if not value:
            return None
        try:
            raw = str(value)
            return date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
        except ValueError:
            return None

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, int | float):
            return float(value)
        try:
            return float(str(value)) if value not in (None, "") else None
        except ValueError:
            return None

    @staticmethod
    def _text(value: object) -> str | None:
        return str(value) if value not in (None, "") else None
