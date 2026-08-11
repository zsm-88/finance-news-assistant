from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.fund.contracts import FundProviderUnauthorizedError
from app.fund.providers.tushare import TushareFundProvider
from app.market.contracts import (
    HistoryPeriod,
    HistoryRange,
    MarketHistoryPoint,
    MarketHistoryResponse,
    MarketInstrument,
    MarketProviderError,
)
from app.market.providers.baostock_history import BaoStockHistoricalMarketProvider
from app.market.repository import MarketHistoryCacheRepository
from app.market.service import MarketHistoryService
from app.wechat.routes import get_fund_service, get_market_history_service, router


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


class FakeHistoryProvider:
    name = "测试历史行情源"

    def __init__(self, *, fails: bool = False) -> None:
        self.calls = 0
        self.fails = fails

    def supports(self, instrument: MarketInstrument, period: HistoryPeriod) -> bool:
        return instrument.market == "CN" and period != "intraday"

    async def fetch_history(
        self,
        instrument: MarketInstrument,
        period: HistoryPeriod,
        history_range: HistoryRange,
    ) -> MarketHistoryResponse:
        self.calls += 1
        if self.fails:
            raise MarketProviderError("timeout")
        point = MarketHistoryPoint(
            timestamp=datetime(2026, 8, 7, tzinfo=UTC),
            open=100,
            high=106,
            low=99,
            close=105,
            volume=1000,
        )
        return MarketHistoryResponse(
            symbol=instrument.symbol,
            name=instrument.name,
            period=period,
            range=history_range,
            items=[point],
            source=self.name,
            as_of=point.timestamp,
            is_delayed=True,
            timezone="Asia/Shanghai",
            status="available",
        )


def test_baostock_parser_orders_filters_and_calculates_ma_boundaries() -> None:
    provider = BaoStockHistoricalMarketProvider(today=lambda: date(2026, 7, 31))
    rows = []
    for day in range(1, 32):
        rows.append(
            {
                "date": f"2026-07-{day:02d}",
                "open": str(day),
                "high": str(day + 1),
                "low": str(max(0.1, day - 1)),
                "close": str(day),
                "volume": str(day * 100),
            }
        )
    rows.reverse()
    rows.append({"date": "bad", "open": "", "high": "", "low": "", "close": ""})

    points = provider._points(rows, "1m")

    assert [point.timestamp.date() for point in points] == sorted(
        point.timestamp.date() for point in points
    )
    assert points[3].ma5 is None
    assert points[4].ma5 == 3
    assert points[9].ma10 == 5.5
    assert points[19].ma20 == 10.5
    assert all(point.timestamp.utcoffset() is not None for point in points)

    sixty = [
        MarketHistoryPoint(
            timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=index),
            open=index + 1,
            high=index + 2,
            low=index + 0.5,
            close=index + 1,
        )
        for index in range(60)
    ]
    provider._apply_moving_averages(sixty)
    assert sixty[58].ma60 is None
    assert sixty[59].ma60 == 30.5


def test_history_contract_rejects_invalid_ohlcv_timezone_and_order() -> None:
    with pytest.raises(ValidationError):
        MarketHistoryPoint(
            timestamp=datetime(2026, 8, 8),  # noqa: DTZ001 - intentionally invalid fixture
            open=10,
            high=9,
            low=8,
            close=11,
            volume=-1,
        )

    first = MarketHistoryPoint(
        timestamp=datetime(2026, 8, 8, tzinfo=UTC),
        open=10,
        high=11,
        low=9,
        close=10,
    )
    second = first.model_copy(update={"timestamp": datetime(2026, 8, 7, tzinfo=UTC)})
    with pytest.raises(ValidationError):
        MarketHistoryResponse(
            symbol="sh000001",
            name="上证指数",
            period="day",
            range="1m",
            items=[first, second],
            source="BaoStock",
            as_of=first.timestamp,
            is_delayed=True,
            timezone="Asia/Shanghai",
            status="available",
        )


@pytest.mark.asyncio
async def test_history_service_uses_cache_and_returns_no_fake_overseas_data() -> None:
    provider = FakeHistoryProvider()
    store = FakeStore()
    service = MarketHistoryService(
        provider,
        MarketHistoryCacheRepository(store, ttl_seconds=300),
    )

    first = await service.history("sh000001", "day", "1m")
    second = await service.history("sh000001", "day", "1m")
    overseas = await service.history("us_spx", "day", "1m")

    assert first == second
    assert provider.calls == 1
    assert store.set_calls == 2
    assert overseas is not None
    assert overseas.status == "unavailable"
    assert overseas.items == []
    assert "暂无可靠" in (overseas.message or "")


@pytest.mark.asyncio
async def test_history_provider_failure_isolated_and_cached() -> None:
    provider = FakeHistoryProvider(fails=True)
    service = MarketHistoryService(provider, MarketHistoryCacheRepository(FakeStore()))
    result = await service.history("sh000001", "day", "1m")
    assert result is not None
    assert result.status == "error"
    assert result.items == []


@pytest.mark.asyncio
async def test_tushare_history_uses_only_official_nav_and_sorts_dates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.read())
        assert body["api_name"] == "fund_nav"
        assert body["fields"] == "ts_code,nav_date,unit_nav,adj_nav"
        assert body["params"]["start_date"]
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "fields": ["ts_code", "nav_date", "unit_nav", "adj_nav"],
                    "items": [
                        ["000001.OF", "20260807", 1.2, 1.3],
                        ["000001.OF", "20260806", 1.1, 1.2],
                        ["000001.OF", "bad", None, None],
                    ],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await TushareFundProvider(client, "test-token").nav_history("000001.OF", "1m")

    assert result.status == "available"
    assert result.is_estimate is False
    assert [item.nav_date for item in result.items] == [date(2026, 8, 6), date(2026, 8, 7)]
    assert result.items[-1].unit_nav == 1.2
    assert result.items[-1].adj_nav == 1.3


@pytest.mark.asyncio
async def test_tushare_permission_error_is_typed_without_exposing_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 40203, "msg": "抱歉，您没有访问该接口的权限"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TushareFundProvider(client, "sensitive-token")
        with pytest.raises(FundProviderUnauthorizedError) as error:
            await provider.nav_history("000001.OF", "1m")
    assert "sensitive-token" not in str(error.value)


class FakeFundHistoryService:
    async def nav_history(self, code: str, history_range: str, refresh: bool) -> dict[str, Any]:
        return {
            "code": code,
            "range": history_range,
            "items": [],
            "source": "Tushare",
            "as_of": None,
            "is_estimate": False,
            "is_stale": False,
            "status": "unauthorized",
            "message": "历史净值数据源未授权",
        }


@pytest.fixture
def history_api_client() -> Iterator[TestClient]:
    market_service = MarketHistoryService(
        FakeHistoryProvider(),
        MarketHistoryCacheRepository(FakeStore()),
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_market_history_service] = lambda: market_service
    app.dependency_overrides[get_fund_service] = lambda: FakeFundHistoryService()
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_history_apis_validate_ranges_and_return_explicit_status(
    history_api_client: TestClient,
) -> None:
    market = history_api_client.get(
        "/api/v1/wechat/market/sh000001/history",
        params={"period": "day", "range": "1m"},
    )
    assert market.status_code == 200
    assert market.json()["items"][0]["volume"] == 1000
    assert market.json()["is_delayed"] is True

    fund = history_api_client.get(
        "/api/v1/wechat/funds/000001.OF/nav-history",
        params={"range": "3m"},
    )
    assert fund.status_code == 200
    assert fund.json()["status"] == "unauthorized"
    assert fund.json()["is_estimate"] is False

    assert history_api_client.get(
        "/api/v1/wechat/market/sh000001/history",
        params={"period": "hour", "range": "1m"},
    ).status_code == 422
    assert history_api_client.get(
        "/api/v1/wechat/funds/000001.OF/nav-history",
        params={"range": "5y"},
    ).status_code == 422
    assert history_api_client.get(
        "/api/v1/wechat/market/unknown/history"
    ).status_code == 404
