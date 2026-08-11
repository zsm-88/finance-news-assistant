import json
from datetime import UTC, date, datetime

import httpx
import pytest

from app.fund.contracts import (
    FundProviderUnauthorizedError,
)
from app.fund.providers.eastmoney_fund_data import (
    HISTORY_SOURCE,
    HOLDINGS_SOURCE,
    EastmoneyExperimentalFundProvider,
)
from app.fund.providers.fallback_fund import FallbackFundProvider


def _epoch(day: int) -> int:
    return int(datetime(2026, 8, day, 7, tzinfo=UTC).timestamp() * 1000)


def _script() -> str:
    unit = [
        {"x": _epoch(7), "y": 3.1808},
        {"x": _epoch(10), "y": 3.2692},
        {"x": "invalid", "y": None},
    ]
    adjusted = [[_epoch(7), 3.1808], [_epoch(10), 3.2692]]
    return (
        'var fS_name = "银华集成电路混合C";'
        f"var Data_netWorthTrend = {json.dumps(unit)};"
        f"var Data_ACWorthTrend = {json.dumps(adjusted)};"
    )


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/013841.js"):
        return httpx.Response(200, text=_script())
    if request.url.host == "qt.gtimg.cn":
        return httpx.Response(
            200,
            content=(
                'v_sh688361="1~中科飞测~688361~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~11.45~3.26";\n'
                'v_sh688037="1~芯源微~688037~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~0~-3.00~-0.96";'
            ).encode("gb18030"),
        )
    assert request.url.path.endswith("/FundMNewApi/FundMNInverstPosition")
    assert request.url.params["FCODE"] == "013841"
    return httpx.Response(
        200,
        json={
            "Success": True,
            "Expansion": "2026-06-30",
            "Datas": {
                "fundStocks": [
                    {"GPDM": "688361", "GPJC": "中科飞测", "JZBL": "10.55"},
                    {"GPDM": "688037", "GPJC": "芯源微", "JZBL": 10.03},
                ]
            },
        },
    )


@pytest.mark.asyncio
async def test_eastmoney_experimental_history_is_official_nav_and_ordered() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        provider = EastmoneyExperimentalFundProvider(
            client, enabled=True, today=lambda: date(2026, 8, 10)
        )
        profile = await provider.profile("013841.OF")
        nav = await provider.official_nav("013841.OF")
        history = await provider.nav_history("013841.OF", "1m")

    assert profile is not None and profile.name == "银华集成电路混合C"
    assert nav.data.value == 3.2692
    assert nav.data.is_estimate is False
    assert nav.data.source == HISTORY_SOURCE
    assert [item.nav_date for item in history.items] == [date(2026, 8, 7), date(2026, 8, 10)]
    assert history.items[-1].adj_nav == 3.2692
    assert history.is_estimate is False


@pytest.mark.asyncio
async def test_eastmoney_experimental_holdings_keep_report_date_and_source() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        provider = EastmoneyExperimentalFundProvider(client, enabled=True)
        result = await provider.holdings("013841.OF")

    assert result.source == HOLDINGS_SOURCE
    assert result.as_of == date(2026, 6, 30)
    assert result.is_stale is True
    assert result.items[0].symbol == "688361"
    assert result.items[0].name == "中科飞测"
    assert result.items[0].weight_percent == 10.55
    assert result.items[0].change_percent == 3.26
    assert result.items[1].change_percent == -0.96


class UnauthorizedProvider:
    name = "Tushare"
    configured = True

    async def catalog(self):
        raise FundProviderUnauthorizedError("unauthorized")

    async def profile(self, code):
        raise FundProviderUnauthorizedError("unauthorized")

    async def official_nav(self, code):
        raise FundProviderUnauthorizedError("unauthorized")

    async def holdings(self, code):
        raise FundProviderUnauthorizedError("unauthorized")

    async def nav_history(self, code, history_range):
        raise FundProviderUnauthorizedError("unauthorized")


@pytest.mark.asyncio
async def test_fallback_uses_eastmoney_when_tushare_is_unauthorized() -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_handler)) as client:
        fallback = EastmoneyExperimentalFundProvider(
            client, enabled=True, today=lambda: date(2026, 8, 10)
        )
        provider = FallbackFundProvider(UnauthorizedProvider(), fallback)
        history = await provider.nav_history("013841.OF", "3m")
        holdings = await provider.holdings("013841.OF")

    assert history.status == "available"
    assert history.source == HISTORY_SOURCE
    assert len(holdings.items) == 2
