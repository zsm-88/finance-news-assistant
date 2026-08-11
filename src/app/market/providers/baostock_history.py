import asyncio
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..contracts import (
    HistoryPeriod,
    HistoryRange,
    MarketHistoryPoint,
    MarketHistoryResponse,
    MarketInstrument,
    MarketProviderError,
)

_RANGE_DAYS: dict[HistoryRange, int] = {
    "1d": 1,
    "1m": 31,
    "3m": 93,
    "6m": 186,
    "1y": 366,
    "5y": 366 * 5,
}
_FREQUENCY: dict[HistoryPeriod, str] = {"day": "d", "week": "w", "month": "m"}
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class BaoStockHistoricalMarketProvider:
    """Official BaoStock client adapter for mainland China EOD history."""

    name = "BaoStock"

    def __init__(self, today: Callable[[], date] | None = None) -> None:
        self.today = today or (lambda: datetime.now(_SHANGHAI).date())
        self._lock = asyncio.Lock()

    def supports(self, instrument: MarketInstrument, period: HistoryPeriod) -> bool:
        return instrument.market == "CN" and period in _FREQUENCY

    async def fetch_history(
        self,
        instrument: MarketInstrument,
        period: HistoryPeriod,
        history_range: HistoryRange,
    ) -> MarketHistoryResponse:
        if not self.supports(instrument, period):
            raise MarketProviderError("BaoStock does not support this instrument or period")
        async with self._lock:
            try:
                rows = await asyncio.to_thread(
                    self._fetch_sync,
                    self._baostock_symbol(instrument.symbol),
                    _FREQUENCY[period],
                    history_range,
                )
            except Exception as exc:
                raise MarketProviderError("BaoStock history request failed") from exc

        points = self._points(rows, history_range)
        return MarketHistoryResponse(
            symbol=instrument.symbol,
            name=instrument.name,
            period=period,
            range=history_range,
            items=points,
            source=self.name,
            as_of=points[-1].timestamp if points else None,
            is_delayed=True,
            timezone="Asia/Shanghai",
            status="available" if points else "unavailable",
            message=None if points else "BaoStock 暂无该时间范围的历史行情",
        )

    def _fetch_sync(
        self,
        symbol: str,
        frequency: str,
        history_range: HistoryRange,
    ) -> list[dict[str, str]]:
        import baostock as bs  # type: ignore[import-not-found]

        end = self.today()
        requested_start = end - timedelta(days=_RANGE_DAYS[history_range])
        query_start = requested_start - timedelta(days=120)
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"BaoStock login failed: {login.error_code}")
        try:
            result = bs.query_history_k_data_plus(
                symbol,
                "date,open,high,low,close,volume",
                start_date=query_start.isoformat(),
                end_date=end.isoformat(),
                frequency=frequency,
                adjustflag="3",
            )
            if result.error_code != "0":
                raise RuntimeError(f"BaoStock query failed: {result.error_code}")
            rows: list[dict[str, str]] = []
            while result.next():
                rows.append(dict(zip(result.fields, result.get_row_data(), strict=False)))
            return rows
        finally:
            bs.logout()

    def _points(
        self,
        rows: list[dict[str, str]],
        history_range: HistoryRange,
    ) -> list[MarketHistoryPoint]:
        parsed: list[MarketHistoryPoint] = []
        for row in rows:
            try:
                day = date.fromisoformat(row["date"])
                values = [float(row[key]) for key in ("open", "high", "low", "close")]
            except (KeyError, TypeError, ValueError):
                continue
            if any(value <= 0 for value in values):
                continue
            volume = self._number(row.get("volume"))
            parsed.append(
                MarketHistoryPoint(
                    timestamp=datetime.combine(day, time(), _SHANGHAI),
                    open=values[0],
                    high=values[1],
                    low=values[2],
                    close=values[3],
                    volume=volume,
                )
            )
        parsed.sort(key=lambda item: item.timestamp)
        self._apply_moving_averages(parsed)
        cutoff = self.today() - timedelta(days=_RANGE_DAYS[history_range])
        return [point for point in parsed if point.timestamp.date() >= cutoff]

    @staticmethod
    def _apply_moving_averages(points: list[MarketHistoryPoint]) -> None:
        closes = [point.close for point in points]
        for index, point in enumerate(points):
            for window, field in ((5, "ma5"), (10, "ma10"), (20, "ma20"), (60, "ma60")):
                if index + 1 >= window:
                    value = sum(closes[index + 1 - window : index + 1]) / window
                    setattr(point, field, round(value, 4))

    @staticmethod
    def _baostock_symbol(symbol: str) -> str:
        if symbol.startswith(("sh", "sz")):
            return f"{symbol[:2]}.{symbol[2:]}"
        raise ValueError("Unsupported BaoStock symbol")

    @staticmethod
    def _number(value: Any) -> float | None:
        try:
            return float(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None
