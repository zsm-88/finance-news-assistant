import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from ..contracts import MarketInstrument, MarketProviderError, MarketQuote
from ..market_hours import market_status

logger = logging.getLogger(__name__)


class YahooFinanceProvider:
    name = "Yahoo Finance"

    def __init__(
        self,
        client: httpx.AsyncClient,
        base_url: str = "https://query1.finance.yahoo.com",
    ) -> None:
        self.client = client
        self.base_url = base_url.rstrip("/")

    async def fetch(
        self,
        instruments: Sequence[MarketInstrument],
    ) -> dict[str, MarketQuote]:
        results = await asyncio.gather(
            *(self._fetch_one(instrument) for instrument in instruments),
            return_exceptions=True,
        )
        quotes: dict[str, MarketQuote] = {}
        for instrument, result in zip(instruments, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "market_provider_request_failed symbol=%s error_type=%s",
                    instrument.symbol,
                    type(result).__name__,
                )
                continue
            quotes[instrument.symbol] = result
        if instruments and not quotes:
            raise MarketProviderError("All market requests failed")
        return quotes

    async def _fetch_one(self, instrument: MarketInstrument) -> MarketQuote:
        symbol = quote(instrument.provider_symbol, safe="")
        response = await self.client.get(
            f"{self.base_url}/v8/finance/chart/{symbol}",
            params={"interval": "1m", "range": "1d"},
        )
        response.raise_for_status()
        payload = response.json()
        result = payload.get("chart", {}).get("result")
        if not result:
            raise ValueError("Market response has no result")
        return self._parse(instrument, result[0])

    def _parse(self, instrument: MarketInstrument, result: dict[str, Any]) -> MarketQuote:
        meta = result.get("meta", {})
        price = self._number(meta.get("regularMarketPrice"))
        previous_close = self._number(meta.get("chartPreviousClose"))
        timestamp_value = meta.get("regularMarketTime")
        if price is None or previous_close is None or timestamp_value is None:
            raise ValueError("Market response is missing price fields")
        change = price - previous_close
        change_percent = change / previous_close * 100 if previous_close else None
        timestamp = datetime.fromtimestamp(float(timestamp_value), UTC)
        status = market_status(instrument.market)
        is_delayed = (
            status == "trading"
            and (datetime.now(UTC) - timestamp).total_seconds() > 15 * 60
        )
        return MarketQuote(
            symbol=instrument.symbol,
            name=instrument.name,
            market=instrument.market,
            asset_type=instrument.asset_type,
            price=round(price, 4),
            change=round(change, 4),
            change_percent=round(change_percent, 4) if change_percent is not None else None,
            timestamp=timestamp,
            market_status=status,
            source=self.name,
            is_delayed=is_delayed,
        )

    @staticmethod
    def _number(value: object) -> float | None:
        if isinstance(value, int | float):
            return float(value)
        return None
