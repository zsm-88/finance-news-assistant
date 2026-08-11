from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.market.contracts import (
    MarketHistoryPoint,
    MarketHistoryResponse,
    MarketInstrument,
    MarketProviderError,
    MarketQuote,
)
from app.market.instruments import INSTRUMENTS
from app.market.market_hours import market_status
from app.market.providers.yahoo import YahooFinanceProvider
from app.market.repository import MarketCacheRepository
from app.market.service import MarketService
from app.wechat.routes import get_market_service, router


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls = 0

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> object:
        assert ex > 0
        self.values[key] = value
        self.set_calls += 1
        return True


class FakeProvider:
    name = "测试行情源"

    def __init__(self, quotes: dict[str, MarketQuote], fails: bool = False) -> None:
        self.quotes = quotes
        self.fails = fails
        self.calls = 0

    async def fetch(
        self,
        instruments: Sequence[MarketInstrument],
    ) -> dict[str, MarketQuote]:
        self.calls += 1
        if self.fails:
            raise MarketProviderError("test provider unavailable")
        return {
            instrument.symbol: self.quotes[instrument.symbol]
            for instrument in instruments
            if instrument.symbol in self.quotes
        }


class FakeHistoryProvider:
    name = "测试历史行情源"

    def __init__(self, items: list[MarketHistoryPoint]) -> None:
        self.items = items

    def supports(self, instrument: MarketInstrument, period: str) -> bool:
        return instrument.market == "CN" and period == "day"

    async def fetch_history(self, instrument, period, history_range):
        return MarketHistoryResponse(
            symbol=instrument.symbol,
            name=instrument.name,
            period=period,
            range=history_range,
            items=self.items,
            source=self.name,
            as_of=self.items[-1].timestamp if self.items else None,
            is_delayed=True,
            timezone="Asia/Shanghai",
            status="available" if self.items else "unavailable",
        )


def quote_for(instrument: MarketInstrument) -> MarketQuote:
    return MarketQuote(
        symbol=instrument.symbol,
        name=instrument.name,
        market=instrument.market,
        asset_type=instrument.asset_type,
        price=105.0,
        change=5.0,
        change_percent=5.0,
        timestamp=datetime(2026, 8, 8, tzinfo=UTC),
        market_status="closed",
        source="测试行情源",
    )


@pytest.mark.asyncio
async def test_yahoo_provider_maps_fields_and_calculates_change() -> None:
    instrument = INSTRUMENTS[0]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/000001.SS")
        return httpx.Response(
            200,
            json={
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "regularMarketPrice": 105,
                                "chartPreviousClose": 100,
                                "regularMarketTime": 1786147200,
                            }
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await YahooFinanceProvider(client).fetch((instrument,))
    quote = result[instrument.symbol]
    assert quote.name == "上证指数"
    assert quote.change == 5
    assert quote.change_percent == 5
    assert quote.source == "Yahoo Finance"


@pytest.mark.asyncio
async def test_yahoo_provider_converts_timeout_to_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("test timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MarketProviderError):
            await YahooFinanceProvider(client).fetch((INSTRUMENTS[0],))


@pytest.mark.asyncio
async def test_service_uses_redis_cache() -> None:
    instrument = INSTRUMENTS[0]
    provider = FakeProvider({instrument.symbol: quote_for(instrument)})
    store = FakeStore()
    service = MarketService(provider, MarketCacheRepository(store, ttl_seconds=60), (instrument,))

    first = await service.quote(instrument.symbol)
    second = await service.quote(instrument.symbol)

    assert first == second
    assert provider.calls == 1
    assert store.set_calls == 2
    assert f"market:{instrument.symbol}" in store.values
    assert f"market:last-valid:{instrument.symbol}" in store.values


@pytest.mark.asyncio
async def test_service_returns_unavailable_quote_when_provider_fails() -> None:
    instrument = INSTRUMENTS[0]
    provider = FakeProvider({}, fails=True)
    store = FakeStore()
    service = MarketService(
        provider,
        MarketCacheRepository(store),
        (instrument,),
    )
    result = await service.quote(instrument.symbol)
    cached = await service.quote(instrument.symbol)
    assert result is not None
    assert result.price is None
    assert result.market_status == "unavailable"
    assert cached == result
    assert provider.calls == 1
    assert store.set_calls == 1


def test_instrument_names_and_market_status_are_localized_and_calculated() -> None:
    assert len(INSTRUMENTS) == 12
    assert {item.name for item in INSTRUMENTS} >= {
        "上证指数",
        "恒生科技指数",
        "纳斯达克指数",
        "黄金",
        "美元指数",
    }
    assert market_status("CN", datetime(2026, 8, 10, 2, 0, tzinfo=UTC)) == "trading"
    assert market_status("CN", datetime(2026, 8, 10, 8, 0, tzinfo=UTC)) == "closed"
    assert market_status("CN", datetime(2026, 8, 8, 2, 0, tzinfo=UTC)) == "weekend"
    assert market_status("CN", datetime(2026, 10, 1, 2, 0, tzinfo=UTC)) == "holiday"
    assert market_status("US", datetime(2026, 8, 10, 12, 0, tzinfo=UTC)) == "pre_market"


@pytest.fixture
def market_client() -> TestClient:
    quotes = {item.symbol: quote_for(item) for item in INSTRUMENTS}
    service = MarketService(
        FakeProvider(quotes),
        MarketCacheRepository(FakeStore()),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_market_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


def test_market_list_and_detail_api(market_client: TestClient) -> None:
    response = market_client.get("/api/v1/wechat/market")
    assert response.status_code == 200
    assert len(response.json()["items"]) == 12
    assert response.json()["items"][0]["name"] == "上证指数"

    detail = market_client.get("/api/v1/wechat/market/sh000001")
    assert detail.status_code == 200
    assert detail.json()["price"] == 105


def test_market_api_rejects_unknown_and_invalid_symbols(market_client: TestClient) -> None:
    assert market_client.get("/api/v1/wechat/market/not_found").status_code == 404
    assert market_client.get("/api/v1/wechat/market/INVALID!").status_code == 422


def test_market_api_returns_empty_quotes_without_fake_prices() -> None:
    service = MarketService(
        FakeProvider({}, fails=True),
        MarketCacheRepository(FakeStore()),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_market_service] = lambda: service
    with TestClient(app) as client:
        response = client.get("/api/v1/wechat/market")
    assert response.status_code == 200
    assert all(item["price"] is None for item in response.json()["items"])
    assert all(item["market_status"] == "unavailable" for item in response.json()["items"])


@pytest.mark.asyncio
async def test_provider_failure_returns_last_valid_quote_without_changing_timestamp() -> None:
    instrument = INSTRUMENTS[0]
    store = FakeStore()
    cache = MarketCacheRepository(store)
    original = quote_for(instrument)
    await cache.set(original)
    store.values.pop(f"market:{instrument.symbol}")
    now = datetime(2026, 8, 9, 4, 0, tzinfo=UTC)
    service = MarketService(
        FakeProvider({}, fails=True),
        cache,
        (instrument,),
        now=lambda: now,
    )

    result = await service.quote(instrument.symbol)

    assert result is not None
    assert result.price == original.price
    assert result.timestamp == original.timestamp
    assert result.market_status == "weekend"
    assert result.is_stale is True
    assert result.is_delayed is True


@pytest.mark.asyncio
async def test_closed_quote_is_stale_without_rewriting_real_values() -> None:
    instrument = INSTRUMENTS[0]
    original = quote_for(instrument)
    service = MarketService(
        FakeProvider({instrument.symbol: original}),
        MarketCacheRepository(FakeStore()),
        (instrument,),
        now=lambda: datetime(2026, 8, 10, 8, 0, tzinfo=UTC),
    )

    result = await service.quote(instrument.symbol)

    assert result is not None
    assert result.market_status == "closed"
    assert result.is_stale is True
    assert result.price == original.price
    assert result.change == original.change
    assert result.timestamp == original.timestamp


@pytest.mark.asyncio
async def test_cn_history_fallback_uses_last_two_real_closes() -> None:
    instrument = INSTRUMENTS[0]
    friday = datetime(2026, 8, 7, tzinfo=UTC)
    items = [
        MarketHistoryPoint(timestamp=friday - timedelta(days=1), open=100, high=102, low=99, close=100, volume=1),
        MarketHistoryPoint(timestamp=friday, open=101, high=106, low=100, close=105, volume=2),
    ]
    service = MarketService(
        FakeProvider({}, fails=True),
        MarketCacheRepository(FakeStore()),
        (instrument,),
        history_provider=FakeHistoryProvider(items),
        now=lambda: datetime(2026, 8, 9, 4, 0, tzinfo=UTC),
    )

    result = await service.quote(instrument.symbol)

    assert result is not None
    assert result.price == 105
    assert result.change == 5
    assert result.change_percent == 5
    assert result.timestamp.date().isoformat() == "2026-08-07"
    assert result.timestamp.hour == 15
    assert result.source == "测试历史行情源"
    assert result.is_stale is True


@pytest.mark.asyncio
async def test_cn_history_fallback_replaces_older_last_valid_cache() -> None:
    instrument = INSTRUMENTS[0]
    store = FakeStore()
    cache = MarketCacheRepository(store)
    old_quote = quote_for(instrument).model_copy(
        update={"price": 105.0, "timestamp": datetime(2026, 8, 7, 7, tzinfo=UTC)}
    )
    await cache.set(old_quote)
    store.values.pop(f"market:{instrument.symbol}")
    items = [
        MarketHistoryPoint(
            timestamp=datetime(2026, 8, 7, tzinfo=UTC),
            open=100,
            high=106,
            low=99,
            close=105,
            volume=1,
        ),
        MarketHistoryPoint(
            timestamp=datetime(2026, 8, 10, tzinfo=UTC),
            open=106,
            high=109,
            low=104,
            close=108,
            volume=2,
        ),
    ]
    service = MarketService(
        FakeProvider({}, fails=True),
        cache,
        (instrument,),
        history_provider=FakeHistoryProvider(items),
        now=lambda: datetime(2026, 8, 10, 13, 0, tzinfo=UTC),
    )

    result = await service.quote(instrument.symbol)

    assert result is not None
    assert result.price == 108
    assert result.change == 3
    assert result.timestamp.date().isoformat() == "2026-08-10"
    assert result.source == "测试历史行情源"
    assert result.market_status == "closed"
    assert result.is_stale is True
