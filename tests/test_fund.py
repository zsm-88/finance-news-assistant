from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import FundPosition
from app.db.repositories import FundPositionRepository, FundWatchlistRepository
from app.fund.contracts import (
    FundEstimateRecord,
    FundHolding,
    FundHoldingsSnapshot,
    FundNavRecord,
    FundProfile,
    FundProviderError,
    FundValue,
)
from app.fund.providers.eastmoney_valuation import EastmoneyFundValuationProvider
from app.fund.providers.fallback_valuation import FallbackFundValuationProvider
from app.fund.providers.sina_valuation import SinaFundValuationProvider
from app.fund.providers.tushare import TushareFundProvider
from app.fund.repository import FundCacheRepository
from app.fund.service import FundService
from app.fund.trading_hours import estimate_is_stale, fund_market_status
from app.wechat.routes import get_fund_service, router

USER_ID = UUID("00000000-0000-0000-0000-000000000001")
TRADING_NOW = datetime(2026, 8, 7, 6, 0, tzinfo=UTC)


class FakeStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, *, ex: int) -> object:
        assert ex > 0
        self.values[key] = value
        self.expirations[key] = ex
        return True


class FakeFundProvider:
    name = "测试正式数据源"

    def __init__(self, configured: bool = True, fails: bool = False) -> None:
        self._configured = configured
        self.fails = fails
        self.catalog_calls = 0
        self.profile_calls = 0
        self.nav_calls = 0
        self.holdings_calls = 0
        self.fund_profile = FundProfile(
            code="000001.OF",
            name="测试基金",
            fund_type="混合型",
            management_company="测试基金公司",
            source=self.name,
        )

    @property
    def configured(self) -> bool:
        return self._configured

    def _check(self) -> None:
        if self.fails or not self.configured:
            raise FundProviderError("unavailable")

    async def catalog(self) -> list[FundProfile]:
        self.catalog_calls += 1
        self._check()
        return [self.fund_profile]

    async def profile(self, code: str) -> FundProfile | None:
        self.profile_calls += 1
        self._check()
        return self.fund_profile if code == self.fund_profile.code else None

    async def official_nav(self, code: str) -> FundNavRecord:
        self.nav_calls += 1
        self._check()
        return FundNavRecord(
            code=code,
            data=FundValue(
                value=1.25,
                source=self.name,
                as_of=date(2026, 8, 7),
                is_estimate=False,
                is_stale=False,
            ),
        )

    async def holdings(self, code: str) -> FundHoldingsSnapshot:
        self.holdings_calls += 1
        self._check()
        return FundHoldingsSnapshot(
            code=code,
            source=self.name,
            as_of=date(2026, 6, 30),
            items=[
                FundHolding(
                    symbol="600000.SH",
                    market_value=100,
                    shares=10,
                    weight_percent=5,
                    report_date=date(2026, 6, 30),
                )
            ],
        )


class FakeValuationProvider:
    name = "测试实验性估值"

    def __init__(
        self,
        *,
        enabled: bool = True,
        stale: bool = False,
        published: bool = False,
        value: float | None = 1.3,
    ) -> None:
        self._enabled = enabled
        self.stale = stale
        self.published = published
        self.value = value
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def fetch(self, codes: list[str]) -> dict[str, FundEstimateRecord]:
        self.calls += 1
        if not self.enabled:
            return {}
        return {
            code: FundEstimateRecord(
                code=code,
                name="测试基金",
                data=FundValue(
                    value=self.value,
                    source=self.name,
                    as_of=TRADING_NOW - timedelta(minutes=1),
                    is_estimate=True,
                    is_stale=self.stale,
                ),
                change_percent=1.23,
                published_nav=(
                    FundValue(
                        value=1.28,
                        source="测试最新公布净值",
                        as_of=date(2026, 8, 7),
                        is_estimate=False,
                        is_stale=False,
                    )
                    if self.published
                    else None
                ),
            )
            for code in codes
        }


def tushare_response(fields: list[str], items: list[list[object]]) -> httpx.Response:
    return httpx.Response(200, json={"code": 0, "msg": None, "data": {"fields": fields, "items": items}})


@pytest.mark.asyncio
async def test_tushare_provider_uses_documented_apis_and_keeps_report_period() -> None:
    called: set[str] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.read())
        assert body["token"] == "test-token"
        called.add(body["api_name"])
        if body["api_name"] == "fund_basic":
            return tushare_response(
                ["ts_code", "name", "management", "fund_type"],
                [["000001.OF", "华夏成长", "华夏基金", "混合型"]],
            )
        if body["api_name"] == "fund_nav":
            return tushare_response(
                ["ts_code", "nav_date", "unit_nav"],
                [["000001.OF", "20260806", 1.1], ["000001.OF", "20260807", 1.2]],
            )
        return tushare_response(
            ["ts_code", "ann_date", "end_date", "symbol", "mkv", "amount", "stk_mkv_ratio"],
            [
                ["000001.OF", "20260720", "20260630", "600001.SH", 200, 20, 8],
                ["000001.OF", "20260420", "20260331", "600002.SH", 100, 10, 4],
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TushareFundProvider(client, "test-token")
        profile = await provider.profile("000001.OF")
        nav = await provider.official_nav("000001.OF")
        holdings = await provider.holdings("000001.OF")

    assert called == {"fund_basic", "fund_nav", "fund_portfolio"}
    assert profile is not None and profile.name == "华夏成长"
    assert nav.data.value == 1.2
    assert nav.data.as_of == date(2026, 8, 7)
    assert holdings.as_of == date(2026, 6, 30)
    assert [item.symbol for item in holdings.items] == ["600001.SH"]


@pytest.mark.asyncio
async def test_experimental_provider_uses_only_estimate_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/mm/newCore/FundValuationLast"
        assert request.url.params["FCODES"] == "161725"
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": [
                    {
                        "FCODE": "161725",
                        "SHORTNAME": "招商中证白酒指数",
                        "NAV": "0.5642",
                        "PDATE": "2026-08-06",
                        "GSZ": "0.5643",
                        "GSZZL": "0.66",
                        "GZTIME": "2026-08-07 13:59",
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = EastmoneyFundValuationProvider(client, enabled=True, now=lambda: TRADING_NOW)
        result = await provider.fetch(["161725.OF"])

    value = result["161725.OF"]
    assert value.data.value == 0.5643
    assert value.change_percent == 0.66
    assert value.data.is_estimate is True
    assert value.data.is_stale is False
    assert value.data.source == "天天基金实验性估值"
    assert value.published_nav is not None
    assert value.published_nav.value == 0.5642
    assert value.published_nav.as_of == date(2026, 8, 6)
    assert value.published_nav.is_estimate is False


@pytest.mark.asyncio
async def test_experimental_provider_missing_fields_and_failures_degrade_safely() -> None:
    def missing_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": True, "data": [{"FCODE": "161725", "NAV": "9.9999"}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(missing_handler)) as client:
        provider = EastmoneyFundValuationProvider(client, enabled=True, now=lambda: TRADING_NOW)
        result = await provider.fetch(["161725.OF"])
    assert result["161725.OF"].data.value is None
    assert result["161725.OF"].data.is_stale is True
    assert result["161725.OF"].published_nav is not None
    assert result["161725.OF"].published_nav.is_stale is True

    def failure_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    async with httpx.AsyncClient(transport=httpx.MockTransport(failure_handler)) as client:
        provider = EastmoneyFundValuationProvider(client, enabled=True)
        with pytest.raises(FundProviderError):
            await provider.fetch(["161725.OF"])


@pytest.mark.asyncio
async def test_sina_experimental_provider_parses_estimate_without_published_nav() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/FdFundService.getEstimateNetworthPic")
        assert request.url.params["symbol"] == "013841"
        return httpx.Response(
            200,
            json={
                "result": {
                    "data": {
                        "networth": [
                            {
                                "pre_date": "2026-08-07",
                                "min_time": "13:59:00",
                                "pre_nav": "3.2746",
                                "growthrate": "0.0294894366",
                            }
                        ]
                    }
                }
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = SinaFundValuationProvider(client, enabled=True, now=lambda: TRADING_NOW)
        result = await provider.fetch(["013841.OF"])

    value = result["013841.OF"]
    assert value.data.value == 3.2746
    assert value.change_percent == 2.9489
    assert value.data.source == "新浪财经实验性估值"
    assert value.data.is_estimate is True
    assert value.data.is_stale is False
    assert value.published_nav is None


@pytest.mark.asyncio
async def test_fallback_valuation_keeps_primary_published_nav() -> None:
    primary = FakeValuationProvider(stale=True, published=True, value=None)
    fallback = FakeValuationProvider()
    fallback.name = "备用实验性估值"
    provider = FallbackFundValuationProvider(primary, fallback)

    result = await provider.fetch(["000001.OF"])

    assert result["000001.OF"].data.source == "备用实验性估值"
    assert result["000001.OF"].name == "测试基金"
    assert result["000001.OF"].published_nav is not None
    assert result["000001.OF"].published_nav.value == 1.28


def test_fund_trading_hours_and_stale_rules_cover_weekends_and_previous_day() -> None:
    assert fund_market_status(TRADING_NOW) == "trading"
    weekend = datetime(2026, 8, 8, 6, 0, tzinfo=UTC)
    assert fund_market_status(weekend) == "weekend"
    holiday = datetime(2026, 10, 1, 6, 0, tzinfo=UTC)
    assert fund_market_status(holiday) == "holiday"
    assert estimate_is_stale(TRADING_NOW - timedelta(minutes=11), TRADING_NOW, 600) is True
    assert estimate_is_stale(TRADING_NOW - timedelta(minutes=1), TRADING_NOW, 600) is False
    assert estimate_is_stale(TRADING_NOW, weekend, 600) is True


def test_closed_fund_nav_is_marked_stale_without_becoming_an_estimate() -> None:
    value = FundValue(
        value=1.2845,
        source="测试正式数据源",
        as_of=date(2026, 8, 7),
        is_estimate=False,
        is_stale=False,
    )

    result = FundService._present_official_nav(value, "weekend")

    assert result.value == 1.2845
    assert result.as_of == date(2026, 8, 7)
    assert result.is_estimate is False
    assert result.is_stale is True


@pytest.fixture
async def fund_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_fund_repositories_restore_soft_deleted_data(fund_session: AsyncSession) -> None:
    watchlists = FundWatchlistRepository(fund_session)
    positions = FundPositionRepository(fund_session)
    first = await watchlists.add_code(USER_ID, "000001.OF")
    assert await watchlists.remove_code(USER_ID, "000001.OF") is True
    restored = await watchlists.add_code(USER_ID, "000001.OF")
    assert restored.id == first.id
    assert restored.deleted_at is None

    await positions.save(USER_ID, "000001.OF", 100, 1)
    assert await positions.remove(USER_ID, "000001.OF") is True
    restored_position = await positions.save(USER_ID, "000001.OF", 200, 1.1)
    assert restored_position.deleted_at is None
    assert float(restored_position.shares) == 200


@pytest.mark.asyncio
async def test_fund_position_database_constraints(fund_session: AsyncSession) -> None:
    fund_session.add(
        FundPosition(user_id=USER_ID, fund_code="000001.OF", shares=0, average_cost=1)
    )
    with pytest.raises(IntegrityError):
        await fund_session.commit()


def make_service(
    session: AsyncSession,
    *,
    provider: FakeFundProvider | None = None,
    valuation: FakeValuationProvider | None = None,
    store: FakeStore | None = None,
) -> FundService:
    return FundService(
        provider or FakeFundProvider(),
        valuation or FakeValuationProvider(),
        FundCacheRepository(
            store or FakeStore(),
            catalog_ttl_seconds=21_600,
            nav_ttl_seconds=1_800,
            holdings_ttl_seconds=21_600,
            valuation_ttl_seconds=20,
        ),
        FundWatchlistRepository(session),
        FundPositionRepository(session),
        USER_ID,
        now=lambda: TRADING_NOW,
    )


@pytest.mark.asyncio
async def test_fund_service_caches_and_calculates_official_and_estimated_position(
    fund_session: AsyncSession,
) -> None:
    provider = FakeFundProvider()
    valuation = FakeValuationProvider()
    store = FakeStore()
    service = make_service(fund_session, provider=provider, valuation=valuation, store=store)
    await service.add_watchlist("000001.OF")
    from app.fund.contracts import FundPositionInput

    await service.save_position("000001.OF", FundPositionInput(shares=100, average_cost=1))
    first = await service.detail("000001.OF")
    second = await service.detail("000001.OF")

    assert first is not None and first.position is not None
    assert first.position.official_market_value == 125
    assert first.position.official_profit == 25
    assert first.position.estimated_market_value == 130
    assert first.position.estimated_profit == 30
    assert first.position.estimated_profit_rate == 30
    assert second == first
    assert provider.profile_calls == provider.nav_calls == provider.holdings_calls == 1
    assert valuation.calls == 1
    assert store.expirations["fund:profile:000001.OF"] == 21_600
    assert store.expirations["fund:nav:000001.OF"] == 1_800
    assert store.expirations["fund:holdings:000001.OF"] == 21_600
    assert store.expirations["fund:valuation:000001.OF"] == 20


@pytest.mark.asyncio
async def test_stale_estimate_never_drives_position_calculations(
    fund_session: AsyncSession,
) -> None:
    service = make_service(fund_session, valuation=FakeValuationProvider(stale=True))
    from app.fund.contracts import FundPositionInput

    await service.save_position("000001.OF", FundPositionInput(shares=100, average_cost=1))
    result = await service.detail("000001.OF")
    assert result is not None and result.position is not None
    assert result.intraday_estimate.is_stale is True
    assert result.position.estimated_market_value is None
    assert result.position.estimated_profit is None
    assert result.position.estimated_profit_rate is None


@pytest.mark.asyncio
async def test_official_nav_uses_last_real_value_when_provider_becomes_unavailable(
    fund_session: AsyncSession,
) -> None:
    store = FakeStore()
    initial = make_service(fund_session, store=store)
    first = await initial.detail("000001.OF")
    assert first is not None and first.official_nav.value == 1.25

    unavailable = make_service(
        fund_session,
        provider=FakeFundProvider(configured=False),
        store=store,
    )
    result = await unavailable.detail("000001.OF", refresh=True)

    assert result is not None
    assert result.official_nav.value == 1.25
    assert result.official_nav.as_of == date(2026, 8, 7)
    assert result.official_nav.is_estimate is False
    assert result.official_nav.is_stale is True
    assert store.expirations["fund:last-valid-nav:000001.OF"] == 2_592_000


@pytest.mark.asyncio
async def test_published_nav_fills_missing_tushare_nav_without_becoming_estimate(
    fund_session: AsyncSession,
) -> None:
    service = make_service(
        fund_session,
        provider=FakeFundProvider(configured=False),
        valuation=FakeValuationProvider(published=True),
    )

    result = await service.detail("000001.OF")

    assert result is not None
    assert result.official_nav.value == 1.28
    assert result.official_nav.source == "测试最新公布净值"
    assert result.official_nav.as_of == date(2026, 8, 7)
    assert result.official_nav.is_estimate is False
    assert result.intraday_estimate.value == 1.3
    assert result.intraday_estimate.is_estimate is True


@pytest.mark.asyncio
async def test_unconfigured_tushare_still_supports_exact_code_estimate_search(
    fund_session: AsyncSession,
) -> None:
    service = make_service(fund_session, provider=FakeFundProvider(configured=False))
    result = await service.search("000001", 20)
    assert result.provider_configured is False
    assert result.experimental_valuation_enabled is True
    assert result.items[0].name == "测试基金"
    assert result.message == "Tushare 尚未配置，历史净值和季度重仓股暂无数据"


@pytest.fixture
async def fund_api_client(fund_session: AsyncSession) -> AsyncIterator[TestClient]:
    service = make_service(fund_session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_fund_service] = lambda: service
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_fund_api_search_watchlist_position_and_detail(fund_api_client: TestClient) -> None:
    search = fund_api_client.get("/api/v1/wechat/funds/search", params={"q": "测试"})
    assert search.status_code == 200
    assert search.json()["items"][0]["code"] == "000001.OF"

    assert fund_api_client.post("/api/v1/wechat/funds/watchlist/000001.OF").status_code == 201
    position = fund_api_client.put(
        "/api/v1/wechat/funds/positions/000001.OF",
        json={"shares": 100, "average_cost": 1},
    )
    assert position.status_code == 200

    watchlist = fund_api_client.get("/api/v1/wechat/funds/watchlist")
    assert watchlist.status_code == 200
    item = watchlist.json()["items"][0]
    assert item["official_nav"]["is_estimate"] is False
    assert item["intraday_estimate"]["is_estimate"] is True
    assert item["position"]["official_profit"] == 25
    assert item["position"]["estimated_profit"] == 30

    detail = fund_api_client.get("/api/v1/wechat/funds/000001.OF")
    assert detail.status_code == 200
    body = detail.json()
    assert body["official_nav"]["value"] == 1.25
    assert body["intraday_estimate"]["value"] == 1.3
    assert body["holdings_report_date"] == "2026-06-30"

    assert fund_api_client.delete("/api/v1/wechat/funds/positions/000001.OF").status_code == 200
    assert fund_api_client.delete("/api/v1/wechat/funds/watchlist/000001.OF").status_code == 200


def test_fund_api_validates_inputs(fund_api_client: TestClient) -> None:
    assert fund_api_client.get("/api/v1/wechat/funds/search", params={"q": ""}).status_code == 422
    assert fund_api_client.get("/api/v1/wechat/funds/INVALID").status_code == 422
    invalid_position = fund_api_client.put(
        "/api/v1/wechat/funds/positions/000001.OF",
        json={"shares": 0, "average_cost": -1},
    )
    assert invalid_position.status_code == 422
